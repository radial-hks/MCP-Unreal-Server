import asyncio
import logging
from typing import Dict, List, Optional

from mcp.server.models import InitializationOptions

# 初始化日志记录器
_logger = logging.getLogger(__name__)
_logger.setLevel(logging.DEBUG)

# 创建文件处理器
file_handler = logging.FileHandler('mcp_unreal.log')
file_handler.setLevel(logging.DEBUG)

# 创建控制台处理器
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)

# 创建日志格式
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)
console_handler.setFormatter(formatter)

# 添加处理器
_logger.addHandler(file_handler)
_logger.addHandler(console_handler)
import mcp.types as types
from mcp.server import NotificationOptions, Server
from pydantic import AnyUrl
import mcp.server.stdio

from .remote_execution import RemoteExecution, RemoteExecutionConfig,MODE_EXEC_FILE,MODE_EXEC_STATEMENT,MODE_EVAL_STATEMENT

class McpUnrealServer:
    def __init__(self):
        self.server = Server("mcp-server-unreal")
        self.remote_execution = None
        self.connected_nodes: Dict[str, dict] = {}
        self._node_monitor_task = None
        self._setup_handlers()

    def _setup_handlers(self):
        @self.server.list_resources()
        async def handle_list_resources() -> list[types.Resource]:
            """列出可用的Unreal节点资源。"""
            resources = []
            if self.remote_execution:
                for node in self.remote_execution.remote_nodes:
                    resources.append(
                        types.Resource(
                            uri=AnyUrl(f"unreal://{node['node_id']}"),
                            name=f"Unreal Instance: {node['node_id']}",
                            description="Unreal Engine实例",
                            mimeType="application/x-unreal",
                        )
                    )
            return resources

        @self.server.list_tools()
        async def handle_list_tools() -> list[types.Tool]:
            """列出可用的工具。"""
            return [
                types.Tool(
                    name="connect-unreal",
                    description="连接到Unreal实例",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "host": {"type": "string", "default": "239.0.0.1"},
                            "port": {"type": "integer", "default": 6766},
                        },
                    },
                ),
                types.Tool(
                    name="execute-python",
                    description="在Unreal中执行Python代码",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "node_id": {"type": "string"},
                            "code": {"type": "string"},
                            "unattended": {"type": "boolean", "default": True},
                        },
                        "required": ["node_id", "code"],
                    },
                ),
            ]

        @self.server.call_tool()
        async def handle_call_tool(
            name: str, arguments: dict | None
        ) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
            """处理工具执行请求。"""
            if name == "connect-unreal":
                return await self._handle_connect_unreal(arguments or {})
            elif name == "execute-python":
                return await self._handle_execute_python(arguments or {})
            raise ValueError(f"未知的工具: {name}")

    async def _handle_connect_unreal(self, arguments: dict) -> list[types.TextContent]:
        """处理Unreal连接请求。"""
        try:
            host = arguments.get("host", "239.0.0.1")
            port = arguments.get("port", 6766)
            _logger.info(f"尝试连接Unreal: host={host}, port={port}")

            if self.remote_execution:
                self.remote_execution.stop()

            config = RemoteExecutionConfig()
            config.multicast_group_endpoint = (host, port)
            
            self.remote_execution = RemoteExecution(config)
            self.remote_execution.start()

            # 等待发现节点
            await asyncio.sleep(2)
            nodes = self.remote_execution.remote_nodes
            
            if not nodes:
                _logger.warning("未发现任何Unreal节点")
                return [types.TextContent(type="text", text="未发现任何Unreal节点")]

            # 更新已连接节点列表
            self.connected_nodes = {node["node_id"]: node for node in nodes}
            await self.server.request_context.session.send_resource_list_changed()

            # 启动节点监控任务
            if self._node_monitor_task:
                self._node_monitor_task.cancel()
            self._node_monitor_task = asyncio.create_task(self._monitor_nodes())

            _logger.info(f"成功连接到Unreal，发现{len(nodes)}个节点")
            _logger.info(f"当前节点列表为: {self.connected_nodes.keys()}")
            return [types.TextContent(
                type="text",
                text=f"成功连接到Unreal，发现{len(nodes)}个节点"
            )]
        except Exception as e:
            _logger.error(f"连接Unreal失败: {str(e)}")
            return [types.TextContent(
                type="text",
                text=f"连接Unreal失败: {str(e)}"
            )]

    async def _handle_execute_python(self, arguments: dict) -> list[types.TextContent]:
        """处理Python代码执行请求。"""
        if not self.remote_execution:
            return [types.TextContent(type="text", text="未连接到Unreal实例")]

        node_id = arguments.get("node_id")
        if not node_id or node_id not in self.connected_nodes:
            _logger.info(f"当前节点列表为: {self.connected_nodes.keys()}")
            return [types.TextContent(type="text", text=f"无效的节点ID: {node_id}")]

        code = arguments.get("code")
        if not code:
            return [types.TextContent(type="text", text="未提供Python代码")]

        unattended = arguments.get("unattended", True)
        # exec_mode = arguments.get("exec_mode", MODE_EXEC_FILE)
        # exec_mode = arguments.get("exec_mode", "EvaluateStatement")
        exec_mode = MODE_EXEC_STATEMENT

        try:
            # 检查节点是否仍然可用
            if node_id not in self.connected_nodes:
                return [types.TextContent(type="text", text="节点已断开连接")]

            # 尝试建立命令连接
            self.remote_execution.open_command_connection(node_id)
            result = self.remote_execution.run_command(
                code, unattended=unattended, exec_mode=exec_mode
            )
            self.remote_execution.close_command_connection()

            if not result.get("success", False):
                return [types.TextContent(
                    type="text",
                    text=f"执行失败: {result.get('result', '未知错误')}"
                )]

            return [types.TextContent(
                type="text",
                text=f"执行结果:\n{result.get('result', '')}"
            )]
        except Exception as e:
            if self.remote_execution:
                self.remote_execution.close_command_connection()
            return [types.TextContent(
                type="text",
                text=f"执行失败: {str(e)}"
            )]

    async def _monitor_nodes(self):
        """监控节点状态的异步任务。"""
        while True:
            try:
                await asyncio.sleep(1)  # 每秒检查一次
                if not self.remote_execution:
                    break

                current_nodes = {node["node_id"]: node for node in self.remote_execution.remote_nodes}
                
                # 检查节点变化
                if current_nodes != self.connected_nodes:
                    self.connected_nodes = current_nodes
                    await self.server.request_context.session.send_resource_list_changed()
            except asyncio.CancelledError:
                break
            except Exception as e:
                _logger.error(f"节点监控错误: {str(e)}")

    async def close(self):
        """关闭服务器和所有连接。"""
        if self._node_monitor_task:
            self._node_monitor_task.cancel()
            try:
                await self._node_monitor_task
            except asyncio.CancelledError:
                pass

        if self.remote_execution:
            self.remote_execution.stop()

async def main():
    server_instance = McpUnrealServer()
    try:
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            await server_instance.server.run(
                read_stream,
                write_stream,
                InitializationOptions(
                    server_name="mcp-server-unreal",
                    server_version="0.1.0",
                    capabilities=server_instance.server.get_capabilities(
                        notification_options=NotificationOptions(),
                        experimental_capabilities={},
                    ),
                ),
            )
    finally:
        server_instance.close()
