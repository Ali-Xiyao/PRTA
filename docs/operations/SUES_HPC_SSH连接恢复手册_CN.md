# SUES-HPC SSH 连接恢复手册

## 适用范围

本手册适用于本机 SSH 配置中的 `sues-hpc` 别名出现以下症状。仓库版本不记录
账号、密码或服务器地址；使用时请将 `<HPC_IP>` 替换为获授权的实际地址：

- Ping 正常且 TCP/22 可连接，但 `ssh` 在 banner、密钥交换或认证阶段超时；
- 服务端返回 `SSH-2.0-OpenSSH_8.7` 后连接长时间无响应；
- OpenSSH/Paramiko 超时后，本机仍存在到 `<HPC_IP>:22` 的
  `Established` 连接；
- 普通非 TTY SSH/SCP 被登录网关关闭，但短 forced-TTY 命令可以执行。

本流程只恢复登录连接。除非用户另行明确授权，不得停止训练、改变 Slurm
作业、重启物理网卡/VPN、关闭代理进程或创建新的 `srun` step。

## 标准决策顺序

### 1. 先区分网络故障和 SSH 握手故障

```powershell
$hpcIp = "<HPC_IP>"
ping -n 2 -w 3000 $hpcIp

$client = [System.Net.Sockets.TcpClient]::new()
try {
    $client.ReceiveTimeout = 6000
    $client.Connect($hpcIp, 22)
    $stream = $client.GetStream()
    $buffer = New-Object byte[] 256
    $read = $stream.Read($buffer, 0, $buffer.Length)
    [Text.Encoding]::ASCII.GetString($buffer, 0, $read).Trim()
} finally {
    $client.Dispose()
}
```

- Ping/TCP/banner 都失败：按网络、VPN、登录网关或平台故障处理，不要不断重试
  SSH。
- 能收到 `SSH-2.0-OpenSSH_8.7`：路由和 sshd 已可达，继续执行本手册的陈旧
  会话清理和单连接恢复。

### 2. 只清理精确识别的陈旧客户端

```powershell
$hpcIp = "<HPC_IP>"
Get-CimInstance Win32_Process |
    Where-Object { $_.Name -match '^(ssh|scp|sftp|python)\.exe$' } |
    Select-Object ProcessId, ParentProcessId, Name, CommandLine

Get-NetTCPConnection -RemoteAddress $hpcIp -RemotePort 22 `
    -ErrorAction SilentlyContinue |
    Select-Object LocalAddress, LocalPort, State, OwningProcess, CreationTime
```

只允许终止已由 PID、启动时间和命令行共同证明属于刚才失败探针的孤儿进程。
例如，超时后遗留的 `python.exe -`/Paramiko 或精确的 canary `ssh.exe` 可以关闭；
训练 Python、队列 runner、`verge-mihomo`、Meta Tunnel 和其他用户进程不得关闭。
代理侧连接会在对应客户端退出后自行进入 FIN/关闭状态。

```powershell
# 先重新读取并验证目标 PID 的 Name/CommandLine，再使用确切 PID。
Stop-Process -Id <verified_orphan_pid> -Force
```

继续前必须确认没有非 `TimeWait`/`Closed` 的服务器连接：

```powershell
Get-NetTCPConnection -RemoteAddress $hpcIp -RemotePort 22 `
    -ErrorAction SilentlyContinue |
    Where-Object { $_.State -notin 'TimeWait', 'Closed' }
```

### 3. 使用唯一 forced-TTY 连接做 canary

不要并行连接。标准恢复命令是：

```powershell
ssh -4 -tt `
  -o IPQoS=none `
  -o ControlMaster=no `
  -o ControlPath=none `
  -o BatchMode=yes `
  -o ConnectTimeout=15 `
  -o ServerAliveInterval=5 `
  -o ServerAliveCountMax=2 `
  sues-hpc "printf SSH_OK; exit"
```

只有明确返回 `SSH_OK` 才算连接恢复。失败后先再次检查本机孤儿连接，不要立刻
发起多条并行重试，也不要因为一次握手失败就重启网卡或代理。

### 4. 短只读命令继续沿用同一参数

```powershell
ssh -4 -tt -o IPQoS=none -o ControlMaster=no -o ControlPath=none `
  -o BatchMode=yes -o ConnectTimeout=15 sues-hpc `
  "<short_read_only_command>; exit"
```

读取 GPU 状态时优先使用已经存在的持久 telemetry 缓存、`squeue` 和 `sstat`。
不要为了每次状态刷新创建新的 `srun --overlap`，否则会消耗长期 allocation 的
Slurm step namespace。

### 5. 多行探针使用“本地文件、哈希、单行 Base64、远端临时文件”

禁止在 PowerShell、SSH、Bash 和 `python -c` 之间嵌套复杂引号。标准方式：

1. 用 `apply_patch` 创建小型本地探针；
2. 本地通过 `py_compile`、Ruff/语法检查；
3. 计算本地 SHA-256；
4. 把文件编码为一行 Base64，通过已经验证的 forced-TTY 会话写入唯一
   `/tmp/<purpose>_<hash-prefix>.py`；
5. 远端 `sha256sum -c` 通过后才执行；
6. 执行结束立即删除这个精确的 `/tmp` 文件；
7. 最后确认本机没有遗留 SSH/TCP 连接。

PowerShell 模板：

```powershell
$local = (Resolve-Path "<local_probe.py>").Path
python -m py_compile $local
python -m ruff check $local

$bytes = [IO.File]::ReadAllBytes($local)
$payload = [Convert]::ToBase64String($bytes)
$hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $local).Hash.ToLower()
$remote = "/tmp/prta_probe_$($hash.Substring(0,16)).py"

if ($remote -notmatch '^/tmp/prta_probe_[0-9a-f]{16}\.py$') {
    throw "unsafe remote temporary path"
}

$command = "umask 077; echo $payload | base64 -d > $remote; " +
    "echo $hash $remote | sha256sum -c -; rc=`$?; " +
    "if [ `$rc -eq 0 ]; then python3 $remote; rc=`$?; fi; " +
    "rm -f $remote; exit `$rc"

ssh -4 -tt -o IPQoS=none -o ControlMaster=no -o ControlPath=none `
  -o BatchMode=yes -o ConnectTimeout=15 `
  -o ServerAliveInterval=5 -o ServerAliveCountMax=2 `
  sues-hpc $command
```

探针不得包含凭据、患者数据、受保护标签或预测。需要回传大文件时，应另行设计
可续传且带分块哈希的传输流程，不能把上述小探针模板当作大文件传输协议。

## 已知失败方式

- 并行或高频 SSH 重试：会放大脆弱登录网关的连接限流。
- 嵌套 PowerShell/SSH/Base64/Python 引号：可能让远端只收到不完整的
  `import`，产生误导性的 `IndentationError`。
- `ssh -tt ... python3 -` 配合 stdin：PTY 不可靠地传递 EOF，可能永久等待并
  留下孤儿 `ssh.exe`。
- 登录网关异常时直接使用非 TTY SCP：小文件也可能被远端关闭。先恢复 canary，
  小型控制探针使用上面的 forced-TTY/哈希方式。
- 无身份核验地 `Stop-Process`、`taskkill`、重启 Meta Tunnel/物理网卡：可能影响
  Codex、本地训练或其他任务，禁止作为默认恢复步骤。

## 本次验证基线（2026-08-17）

- 清理精确识别的孤儿 Paramiko PID 后，活动服务器 TCP 连接归零；
- 标准 canary 在约两秒内返回 `SSH_OK`；
- forced-TTY/Base64 临时探针远端 SHA-256 校验通过并成功执行；
- 整个恢复过程没有发送服务器进程信号、没有创建新 `srun` step，也没有影响
  四卡训练；
- 结束后本机 `ssh/scp/sftp` 进程和活动服务器 TCP 连接均为零。
