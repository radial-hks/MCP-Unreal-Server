# MCP Unreal Server

A server implementation for interacting with Unreal Engine instances through remote Python execution.

## Features

- 🚀 **Unreal Instance Management**
  - Automatic discovery of Unreal nodes via multicast
  - Real-time node status monitoring
  - Resource listing through LSP-compatible clients

- 💻 **Remote Execution**
  - Execute Python code in Unreal Engine environments
  - Support for both attended and unattended execution modes
  - File execution and statement evaluation modes

- 📊 **Logging & Monitoring**
  - Detailed logging to file (`mcp_unreal.log`)
  - Console logging with different verbosity levels
  - Node connection health monitoring

## Installation

```bash
# Clone repository
git clone https://github.com/your-org/mcp-unreal-server.git
cd mcp-unreal-server

# Install dependencies
pip install -r requirements.txt
```

## Configuration

### Network Settings
Configure multicast parameters in `RemoteExecutionConfig`:
```python
# Default multicast settings (modify in server.py)
config.multicast_group_endpoint = ("239.0.0.1", 6766)
```

### Logging
Modify logging configuration in `server.py`:
```python
# Adjust log levels
file_handler.setLevel(logging.DEBUG)  # File logging
console_handler.setLevel(logging.INFO)  # Console logging
```

## Usage

### Starting the Server
```bash
python -m src.mcp_server_unreal.server
```

### Supported Tools

1. **Connect to Unreal Instance**
```json
{
  "host": "239.0.0.1",
  "port": 6766
}
```

2. **Execute Python Code**
```json
{
  "node_id": "<unreal-node-id>",
  "code": "print('Hello Unreal')",
  "unattended": true
}
```

## API Documentation

### Resource Format
```python
types.Resource(
    uri="unreal://<node_id>",
    name=f"Unreal Instance: {node_id}",
    description="Unreal Engine instance",
    mimeType="application/x-unreal"
)
```

### Execution Modes
| Mode                 | Description                     |
|----------------------|---------------------------------|
| MODE_EXEC_FILE       | Execute Python file             |
| MODE_EXEC_STATEMENT  | Execute Python statement        |
| MODE_EVAL_STATEMENT  | Evaluate Python expression      |

## Troubleshooting

**Common Issues:**
- No nodes discovered: Verify Unreal instances are running with MCP plugin
- Execution timeout: Check firewall settings for multicast traffic
- Connection drops: Monitor `mcp_unreal.log` for node status changes

## License
Apache-2.0 License