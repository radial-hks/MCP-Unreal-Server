import asyncio
import logging
import time
from typing import Dict, List, Optional, AsyncIterator, Any
from contextlib import asynccontextmanager
from collections import deque

from mcp.server.models import InitializationOptions

# Configure logging
logging.basicConfig(level=logging.INFO,
                format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
_logger = logging.getLogger("UnrealMCPServer")

# 添加这一行来降低 mcp.server.lowlevel.server 的日志级别
# 初始设置为Error等级,导致在Cline中存在警告信息,故降低日志级别
logging.getLogger("mcp.server.lowlevel.server").setLevel(logging.WARNING)

# Configure file handler with more concise format for frequent operations
file_handler = logging.FileHandler('mcp_unreal.log')
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(logging.Formatter('%(asctime)s.%(msecs)03d - %(levelname).1s - %(message)s', '%H:%M:%S'))
_logger.addHandler(file_handler)

# Configure console handler with detailed format
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
_logger.addHandler(console_handler)

import mcp.types as types
from mcp.server import NotificationOptions, Server
from pydantic import AnyUrl
import mcp.server.stdio

from .remote_execution import RemoteExecution, RemoteExecutionConfig,MODE_EXEC_FILE,MODE_EXEC_STATEMENT,MODE_EVAL_STATEMENT

# 全局连接变量
_unreal_connection: Optional[RemoteExecution] = None
_node_monitor_task: Optional[asyncio.Task] = None

def get_unreal_connection(host: str = "239.0.0.1", port: int = 6766) -> RemoteExecution:
    """获取或创建持久化的Unreal连接"""
    global _unreal_connection
    
    # 如果已有连接，检查是否仍然有效
    if _unreal_connection is not None:
        try:
            nodes = _unreal_connection.remote_nodes
            return _unreal_connection
        except Exception as e:
            _logger.warning(f"现有连接已失效: {str(e)}")
            try:
                _unreal_connection.stop()
            except:
                pass
            _unreal_connection = None
    
    # 创建新连接
    if _unreal_connection is None:
        config = RemoteExecutionConfig()
        config.multicast_group_endpoint = (host, port)
        _unreal_connection = RemoteExecution(config)
        _unreal_connection.start()
        _logger.info("创建新的持久化Unreal连接")
    
    return _unreal_connection

class McpUnrealServer:
    def __init__(self, server_name: str, lifespan=None):
        self.server = Server(server_name, lifespan=lifespan)
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
            return  [
                types.Tool(
                    name="execute-python",
                    description="在Unreal中执行Python代码",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "code": {"type": "string"},
                            "unattended": {"type": "boolean", "default": True},
                        },
                        "required": ["code"],
                    },
                ),
            ]

        # 添加资源模板处理器
        @self.server.list_resource_templates()
        async def handle_list_resource_templates() -> list[types.ResourceTemplate]:
            """列出可用的资源模板。"""
            return []

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
        global _unreal_connection
        
        # 确保连接存在且有效
        try:
            if not _unreal_connection or not _unreal_connection.remote_nodes:
                _unreal_connection = get_unreal_connection()
                # 等待一小段时间以确保连接建立
                await asyncio.sleep(1)
                
            if not _unreal_connection or not _unreal_connection.remote_nodes:
                return [types.TextContent(type="text", text="无法连接到Unreal实例，请确保Unreal正在运行并启用了远程执行")]
        except Exception as e:
            return [types.TextContent(type="text", text=f"连接Unreal失败: {str(e)}")]

        code = arguments.get("code")
        if not code:
            return [types.TextContent(type="text", text="未提供Python代码")]

        unattended = arguments.get("unattended", True)
        exec_mode = MODE_EXEC_STATEMENT

        try:
            # 获取第一个可用节点
            nodes = _unreal_connection.remote_nodes
            if not nodes:
                return [types.TextContent(type="text", text="未发现任何Unreal节点")]
            
            node_id = nodes[0]["node_id"]
            _unreal_connection.open_command_connection(node_id)
            
            result = _unreal_connection.run_command(
                code, unattended=unattended, exec_mode=exec_mode
            )
            _unreal_connection.close_command_connection()

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
            if _unreal_connection:
                try:
                    _unreal_connection.close_command_connection()
                except:
                    pass
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

@asynccontextmanager
async def server_lifespan(server: Server) -> AsyncIterator[Dict[str, Any]]:
    """管理服务器启动和关闭生命周期"""
    try:
        # 记录服务器启动
        _logger.info("UnrealMCP服务器正在启动")
        
        # 尝试在启动时连接到Unreal
        try:
            # 这将初始化全局连接
            unreal = get_unreal_connection()
            _logger.info("成功连接到Unreal")
        except Exception as e:
            _logger.warning(f"无法在启动时连接到Unreal: {str(e)}")
            _logger.warning("请确保Unreal实例正在运行并启用了远程执行")
        
        # 返回空上下文 - 我们使用全局连接
        yield {}
    finally:
        # 在关闭时清理全局连接
        global _unreal_connection, _node_monitor_task
        if _node_monitor_task:
            _node_monitor_task.cancel()
            try:
                await _node_monitor_task
            except asyncio.CancelledError:
                pass
            _node_monitor_task = None
            
        if _unreal_connection:
            _logger.info("正在断开与Unreal的连接")
            _unreal_connection.stop()
            _unreal_connection = None
        _logger.info("UnrealMCP服务器已关闭")

async def main():
    unreal_server = McpUnrealServer("mcp-server-unreal", lifespan=server_lifespan)
    try:
        # 使用实例中的server对象来保持handler注册一致性
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            await unreal_server.server.run(
                read_stream,
                write_stream,
                InitializationOptions(
                    server_name="mcp-server-unreal",
                    server_version="0.1.0",
                    capabilities=unreal_server.server.get_capabilities(
                        notification_options=NotificationOptions(),
                        experimental_capabilities={},
                    ),
                ),
            )
    finally:
        unreal_server.close()