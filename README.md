# Weather Pusher - 天气推送助手

一个基于和风天气 API 和飞书机器人，用于监控天气并发送预警通知的 Python 脚本。

它可以根据您的配置，每日定时推送天气预报，并在未来几小时内有强降雨时发送实时预警。

## ✨ 主要功能

- **每日天气预报**：在每天指定时间，向飞书群组推送包含当天和未来天气的详细预报。
- **实时降雨提醒**：周期性检查未来几小时天气，当检测到中雨及以上强度的降雨时，立即发送实时预警。
- **恶劣天气预警**：在每日预报中，会特别提示未来三天内的恶劣天气（如暴雪、台风、雾霾等）。
- **高度可配置**：通过 `config.ini` 文件，您可以轻松配置地点、推送时间、飞书机器人地址等。
- **稳定运行**：包含日志记录和程序崩溃后自动重启的机制，确保长期稳定监控。

## ⚙️ 运行环境

- Python 3.6 或更高版本

## 🚀 安装与配置

### 步骤 1: 下载项目

将本项目下载到您的服务器或本地电脑。

```bash
git clone [您的仓库地址]
cd Weather-Pusher
```

### 步骤 2: 安装依赖

本项目依赖 `requests` 库用于发送网络请求。请运行以下命令安装：

```bash
pip install -r requirements.txt
```
*如果您系统中同时有 Python 2 和 Python 3，请使用 `pip3`。*

### 步骤 3: 修改配置文件 `config.ini`

这是最关键的一步。请根据文件内的注释，修改 `config.ini` 文件。

**重要提示：`config.ini` 包含您的个人密钥，请绝对不要将此文件上传到 GitHub！**

```ini
[API]
# 1. 你的飞书群机器人 Webhook 地址
# 获取方法：在飞书群组 -> 设置 -> 群机器人 -> 添加机器人 -> 选择“自定义机器人”
feishu_webhook_url = https://open.feishu.cn/open-apis/bot/v2/hook/xxxxxxxx

# 2. 和风天气 Web API Key
# 获取方法：登录和风天气开发者平台(https://dev.qweather.com/) -> 应用管理 -> 创建应用 -> 获取 Key
qweather_key = xxxxxxxxxxxxxxxx

# 3. 和风天气 API 地址 (如果使用免费订阅，请保持默认)
api_host = https://devapi.qweather.com

[Location]
# 4. 需要监控的地点坐标 (经度,纬度)
# 获取方法：可以使用 https://lbs.amap.com/tools/picker 之类的工具获取
location = 116.40,39.90

# 5. 地点的自定义名称，会显示在推送消息中
name = 北京市东城区

[Settings]
# 6. 每日推送的小时 (24小时制)
daily_push_hour = 8

# 7. 每日推送的分钟
daily_push_minute = 0

# 8. 检查未来降雨的间隔分钟数 (建议 15-30 分钟)
check_interval_minutes = 15
```

## ▶️ 如何运行

### 1. 测试运行

在启动主程序前，强烈建议先发送一条测试消息，以确认配置是否正确。

```bash
python3 weater_monitor.py --test
```
如果您的飞书群组收到了测试消息，说明配置无误。

### 2. 启动主程序

直接运行主脚本即可启动监控。程序会在后台持续运行。

```bash
python3 weater_monitor.py
```

### 3. 在服务器上后台运行

如果您希望在关闭终端后程序依然运行，可以使用 `nohup`：

```bash
nohup python3 weater_monitor.py &
```
这会在当前目录下生成一个 `nohup.out` 文件，用于记录程序的标准输出。

## 📄 日志

脚本运行过程中，所有操作和API返回信息都会被记录在 `weather_monitor.log` 文件中。如果程序运行不正常，请优先检查此文件。
