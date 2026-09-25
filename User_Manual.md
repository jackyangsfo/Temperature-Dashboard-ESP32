# Temperature Dashboard — 用户说明书 / User Manual

温湿度电子纸仪表盘（XIAO ESP32-S3 + BME280 + Waveshare 4.2" e-Paper）

---

## 1. 包装与供电

- 使用 **USB-C** 供电（充电器、充电宝或电脑 USB 口均可）。
- 仅供电时不必连接电脑。
- 传感器与屏幕需正确接线并由设备供电后才会工作。

**重要：** 本机 WiFi 仅支持 **2.4 GHz**（不支持 5 GHz）。

---

## 2. 第一次开机 — 配置家里的 WiFi

出厂时设备尚未保存 WiFi。按下列步骤用手机完成配网（无需电脑）：

1. 给设备通电。
2. 等待电子纸刷新。屏幕**底部**会出现类似：
   ```text
   TempDash-XXXX  pw setup1234
   ```
   （`XXXX` 为设备编号，每台可能不同。）
3. 用手机打开 WiFi 列表，连接热点：
   - **名称：** `TempDash-XXXX`（与屏幕一致）
   - **密码：** `setup1234`
4. 打开手机浏览器，访问：
   ```text
   http://192.168.4.1
   ```
5. 在网页中输入：
   - 家里的 **WiFi 名称（SSID）**
   - **WiFi 密码**
   - 必须是 **2.4 GHz** 网络  
6. 点击 **Save and connect**（保存并连接）。
7. 可断开手机与 `TempDash-XXXX` 的连接。设备会加入你家的 WiFi。
8. 成功后，屏幕底部显示类似：
   ```text
   WiFi 192.168.x.x
   ```
   即表示联网成功（`192.168.x.x` 为设备局域网 IP）。

---

## 3. 以后更换 WiFi（改路由器 / 改密码）

不需要电脑。当家里的 WiFi 名称或密码变更后：

1. 保持设备通电。
2. 设备会自动用旧密码重试连接。
3. **大约 3 分钟内**（默认：连续失败 3 次）仍连不上时，会再次打开配网热点。
4. 屏幕底部重新出现：
   ```text
   TempDash-XXXX  pw setup1234
   ```
5. 按 **第 2 节** 相同步骤，用手机输入**新的** WiFi 名称和密码。

### 重试时间说明（默认）

| 项目 | 默认值 | 说明 |
|------|--------|------|
| 每次连接等待 | 约 20 秒 | 单次尝试上限 |
| 失败后间隔 | 约 60 秒 | 再试前等待 |
| 连续失败次数 | 3 次 | 达到后打开配网热点 |
| **合计** | **约 3 分钟** | 之后出现 `TempDash-XXXX` |

> 若设备**从未**成功连过网：第一次约 20 秒连不上就会直接打开配网热点。

---

## 4. 屏幕显示说明

屏幕通常显示：

- **日期 / 时间**（联网后通过 NTP 自动对时；约每分钟随电子纸刷新）  
- 温度 / 湿度 / 气压  
- 露点、舒适度、气压趋势  
- 温度历史曲线  
- **底部一行：** WiFi 状态  

未联网或尚未对时成功时，日期/时间可能显示为 `--` / `--:--`。

时区在设备配置中设置（默认美国太平洋 `TIMEZONE_OFFSET_HOURS = -7`）。

| 底部文字 | 含义 |
|----------|------|
| `TempDash-XXXX  pw setup1234` | 请用手机配网 |
| `WiFi 192.168.x.x` | 已连接，显示本机 IP |
| `WiFi ...` | 正在连接 |
| `WiFi fail` | 连接失败，稍后会重试；多次失败后进入配网 |

---

## 5. 日常使用

- 通电后自动测温并刷新电子纸。
- 温度等读数约每几秒更新一次（内部）；电子纸约每 **60 秒** 刷新一次画面（以减少闪烁与耗电）。
- 拔掉电脑 USB 后，只要仍有 USB 供电（充电器/充电宝），设备会继续运行。

---

## 6. 常见问题

**Q：手机搜不到 `TempDash-XXXX`？**  
A：确认设备已通电；等待屏幕底部出现配网文字后再搜；靠近设备重试。

**Q：网页打不开 192.168.4.1？**  
A：确认手机已连上 `TempDash-XXXX`（不要连家里的 WiFi）；可关掉手机移动数据后再打开该地址。

**Q：保存后连不上家里 WiFi？**  
A：确认是 **2.4 GHz**；密码无误；路由器未开启仅 5G / 访客网络限制。等待约 3 分钟后可再次进入配网重试。

**Q：屏幕很久不更新？**  
A：电子纸约每分钟刷一次属正常。若完全无变化，检查供电后重新插拔 USB 电源。

---

## 7. First-time WiFi setup (English)

1. Power on the device.  
2. Wait until the e-paper footer shows: `TempDash-XXXX  pw setup1234`.  
3. On your phone, join WiFi **TempDash-XXXX** with password **setup1234**.  
4. Open a browser to **http://192.168.4.1**.  
5. Enter your home **2.4 GHz** WiFi name and password → Save.  
6. When done, the footer shows `WiFi 192.168.x.x`.

### Changing WiFi later

After your home WiFi name/password changes, the device retries for about **3 minutes**, then reopens the `TempDash-XXXX` hotspot. Repeat the steps above with the new credentials.

---

## 8. 安全提示

- 配网热点默认密码为 `setup1234`。量产前如需更改，请修改设备配置中的 `WIFI_AP_PASSWORD`。  
- 请勿将含真实家庭 WiFi 密码的测试配置文件随产品寄出。  
- BME280 请使用 **3.3V**；电子纸模块优先使用 **5V**（按产品接线说明）。
