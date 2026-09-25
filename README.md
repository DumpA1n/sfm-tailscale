# sfm-tailscale

让 SFM（sing-box for macOS）通过内置的 `tailscale` endpoint 接入 tailnet，取代 Tailscale.app。两个 TUN 同时开启会互相抢占默认路由和系统 DNS，导致断网。

`serve.py` 监听 `127.0.0.1:18080`。每次收到请求时：拉取上游订阅，打补丁，执行 `sing-box check`，然后返回结果。SFM 把这个地址当作远程 profile 订阅，定时刷新和重载都由 SFM 自己完成。拉取、补丁或校验任一步失败时返回 502，SFM 继续使用当前配置。

脚本不读写 SFM 的 group container：macOS 禁止后台进程访问其他 app 的 group container。

## 补丁内容

| 位置 | 改动 |
|---|---|
| `endpoints` | 新增 `tailscale` endpoint `ts-ep`，`state_directory: tailscale` |
| `dns.servers` | 新增 `DNS-TS`（`type: tailscale`） |
| `dns.rules` 首条 | `ts.net` → `DNS-TS`，排在 fakeip 规则之前 |
| `route.rules` 首条 | `100.64.0.0/10` → `ts-ep` |
| TUN `route_exclude_address` | 删除 `100.64.0.0/10` |

只路由 IPv4：订阅里 TUN 只有 IPv4 地址。

## 文件

| 文件 | 说明 |
|---|---|
| `serve.py` | 补丁代理 |
| `install.sh` | 写入 `subscription.url`，安装并启动 LaunchAgent `com.ddd.sfm-tailscale` |
| `uninstall.sh` | 移除 LaunchAgent |
| `subscription.url` | 上游订阅地址，权限 600，不入库 |
| `auth-key.txt` | 可选，Tailscale auth key，不入库 |
| `serve.log` | 访问与错误日志 |

## 安装

```sh
./install.sh            # 从 SFM 的 remote profile "sakura" 读取订阅地址
./install.sh '<url>'    # 或显式指定
```

然后：

1. 退出 Tailscale.app。
2. 在 SFM 中新建 remote profile，URL 填 `http://127.0.0.1:18080/?log=info`，开启自动更新，选中后连接。
3. 在 SFM 的日志里找到 Tailscale 登录 URL，用浏览器打开并授权。节点身份保存在 SFM 的 `state_directory` 中，之后无需再次登录。
4. 把 profile 的 URL 改回 `http://127.0.0.1:18080/`，恢复订阅原本的日志级别。

也可以不走 URL 登录：在 Tailscale 后台（Settings → Keys）生成 auth key，写入 `auth-key.txt`，然后跳过第 3、4 步。
