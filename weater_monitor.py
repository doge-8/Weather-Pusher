#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import requests
import datetime
import time
import warnings
import configparser
import sys
import json
import logging
from logging.handlers import RotatingFileHandler
from urllib3.exceptions import NotOpenSSLWarning

# 屏蔽 NotOpenSSLWarning 警告
warnings.simplefilter("ignore", NotOpenSSLWarning)

def setup_logging():
    """配置日志系统，支持控制台和文件轮转"""
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    # 创建一个格式化器
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    
    # 配置控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # 配置文件处理器，实现日志轮转
    # 当文件达到1MB时轮转，最多保留5个备份文件
    file_handler = RotatingFileHandler(
        'weather_monitor.log', maxBytes=1*1024*1024, backupCount=5, encoding='utf-8'
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

class WeatherMonitor:
    """
    一个用于监控天气并发送通知的类。
    """
    WEATHER_ICONS = {
        "晴": "☀️", "多云": "⛅", "阴": "☁️", "小雨": "🌧", "中雨": "🌧",
        "大雨": "🌧", "阵雨": "🌦", "雷阵雨": "⛈", "雪": "❄️", "雾": "🌫", "霾": "🌫",
    }

    def __init__(self, config_path='config.ini'):
        """使用配置文件初始化监控器。"""
        self.logger = logging.getLogger(__name__)
        self.config = configparser.ConfigParser()
        self.config.read(config_path, encoding='utf-8') # 指定UTF-8编码
        self._load_config()
        
        self.rain_active = False
        self.last_daily_push_date = None
        self.session = requests.Session()

    def _load_config(self):
        """从解析过的文件中加载配置。"""
        # API 配置
        self.feishu_webhook_url = self.config.get('API', 'feishu_webhook_url')
        self.qweather_key = self.config.get('API', 'qweather_key')
        self.api_host = self.config.get('API', 'api_host')
        
        # 位置配置
        self.location = self.config.get('Location', 'location')
        self.location_name = self.config.get('Location', 'name')

        # 程序设置
        self.daily_push_hour = self.config.getint('Settings', 'daily_push_hour')
        self.daily_push_minute = self.config.getint('Settings', 'daily_push_minute')
        self.check_interval_minutes = self.config.getint('Settings', 'check_interval_minutes')
        self.rain_threshold_precip = self.config.getfloat('Settings', 'rain_threshold_precip')
        self.rain_threshold_pop = self.config.getint('Settings', 'rain_threshold_pop')

    def _request_with_retry(self, url, max_retry=5, delay=3):
        """带重试逻辑的网络请求。"""
        for attempt in range(max_retry):
            try:
                resp = self.session.get(url, timeout=10)
                resp.raise_for_status()  # 对错误的HTTP状态码抛出异常
                return resp.json()
            except requests.exceptions.RequestException as e:
                self.logger.warning(f"请求失败，第 {attempt + 1} 次尝试: {e}")
                time.sleep(delay)
        self.logger.error("超过最大重试次数，跳过本次请求。")
        return None

    def push_to_feishu(self, title, content, max_retry=5, delay=3):
        """带重试逻辑推送飞书通知。"""
        self.logger.info(f"正在推送飞书消息：{title}")
        
        # 飞书卡片消息颜色主题映射
        card_template = "blue"
        if "⚠️" in title or "预警" in title:
            card_template = "red"
        elif "📢" in title:
            card_template = "green"

        data = {
            "msg_type": "interactive",
            "card": {
                "config": {"wide_screen_mode": True},
                "header": {
                    "template": card_template,
                    "title": {"content": title, "tag": "plain_text"}
                },
                "elements": [{"tag": "div", "text": {"content": content, "tag": "lark_md"}}]
            }
        }
        
        for attempt in range(max_retry):
            try:
                resp = self.session.post(self.feishu_webhook_url, json=data, timeout=10)
                resp.raise_for_status()
                resp_json = resp.json()
                if resp_json.get("StatusCode") == 0 or resp_json.get("code") == 0:
                    self.logger.info("飞书消息推送成功。")
                    return True
                else:
                    self.logger.warning(f"飞书消息推送返回异常: {resp_json}")
            except requests.exceptions.RequestException as e:
                self.logger.warning(f"推送失败，第 {attempt + 1} 次尝试: {e}")
            
            time.sleep(delay)

        self.logger.error("超过最大重试次数，跳过本次推送。")
        return False

    def get_daily_weather(self):
        """获取未来3天天气预报的原始数据列表。"""
        self.logger.info("正在获取未来3天天气...")
        url = f"{self.api_host}/v7/weather/3d?location={self.location}&key={self.qweather_key}"
        resp = self._request_with_retry(url)
        if not resp or resp.get('code') != '200':
            self.logger.error(f"获取3天天气失败。API响应: {resp}")
            return None
        
        self.logger.info("未来3天天气获取完成。")
        return resp.get("daily", [])

    def get_hourly_weather(self):
        """获取未来6小时天气，并返回结构化数据列表。"""
        self.logger.info("正在获取未来6小时天气...")
        url = f"{self.api_host}/v7/weather/24h?location={self.location}&key={self.qweather_key}"
        resp = self._request_with_retry(url)
        if not resp or resp.get('code') != '200':
            self.logger.error(f"获取未来6小时天气失败。API响应: {resp}")
            return []

        now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))
        next_6_hours = now + datetime.timedelta(hours=6)
        
        hourly_forecasts = []

        for item in resp.get("hourly", []):
            fx_time = datetime.datetime.fromisoformat(item["fxTime"].replace("Z", "+00:00")).astimezone(datetime.timezone(datetime.timedelta(hours=8)))
            if now <= fx_time <= next_6_hours:
                hourly_forecasts.append({
                    "time": fx_time.strftime('%H:%M'),
                    "text": item.get("text", ""),
                    "pop": int(item.get("pop", "0")),
                })
        
        self.logger.info(f"未来6小时天气获取完成，共 {len(hourly_forecasts)} 条数据。")
        return hourly_forecasts

    def _handle_daily_push(self, now):
        """处理每日定时推送逻辑，并生成动态标题和检查未来预警。"""
        if now.hour == self.daily_push_hour and now.minute == self.daily_push_minute:
            today_str = now.strftime("%Y-%m-%d")
            if self.last_daily_push_date != today_str:
                self.logger.info(f"到达每日推送时间 {self.daily_push_hour:02}:{self.daily_push_minute:02}，准备推送...")
                
                forecast_data = self.get_daily_weather()
                if not forecast_data:
                    self.logger.error("获取3天天气失败，跳过本次推送。")
                    return

                # --- 格式化今日天气 ---
                today_data = forecast_data[0]
                day_text = today_data.get('textDay', '')
                night_text = today_data.get('textNight', '')
                weather_summary = day_text if day_text == night_text else f"{day_text}转{night_text}"
                
                daily_content = (
                    f"📅 **今日天气 · {weather_summary}**  \n"
                    f"🌡 气温：{today_data.get('tempMin', 'N/A')} ~ {today_data.get('tempMax', 'N/A')}℃  \n"
                    f"💨 风力：{today_data.get('windDirDay', '')} {today_data.get('windScaleDay', '')}级  \n"
                    f"💧 湿度：{today_data.get('humidity', 'N/A')}%"
                )

                # --- 检查未来3天天气事件 ---
                rain_alerts, other_severe_alerts = [], []
                rain_days_indices, severe_days_indices = [], []
                
                # 根据您的最终方案定义关键词
                rain_keywords = ["阵雨", "中雨", "大雨", "暴雨", "极端降雨"]
                other_severe_keywords = ["冰雹", "台风", "雪", "暴雪", "大雪", "沙尘暴", "雾", "霾", "冻雨", "雨夹雪"]

                for daily_forecast in forecast_data:
                    precip_mm = float(daily_forecast.get('precip', '0.0'))
                    text_day = daily_forecast.get('textDay', '')
                    text_night = daily_forecast.get('textNight', '')
                    text_to_check = text_day + text_night
                    
                    date_obj = datetime.datetime.strptime(daily_forecast.get('fxDate'), '%Y-%m-%d').date()
                    days_diff = (date_obj - now.date()).days
                    day_map = {0: "今天", 1: "明天", 2: "后天"}
                    date_prefix = day_map.get(days_diff, daily_forecast.get('fxDate'))

                    # --- 检查降雨事件（最终融合方案）---
                    # 1. 检查关键字定义的降雨
                    is_rain_by_keyword = any(k in text_to_check for k in rain_keywords)

                    # 2. 检查降水量达标且含“雨”字的降雨
                    is_rain_by_precip = (precip_mm >= 5.0 and '雨' in text_to_check)

                    # 满足任一条件即为需要提醒的降雨
                    if is_rain_by_keyword or is_rain_by_precip:
                        rain_alerts.append(f"∙ **{date_prefix}**: {text_day}，预计降水 {precip_mm}mm")
                        if days_diff in day_map: rain_days_indices.append(days_diff)

                    # --- 检查其他恶劣天气 ---
                    for keyword in other_severe_keywords:
                        if keyword in text_to_check:
                            other_severe_alerts.append(f"∙ **{date_prefix}**: {text_day}")
                            if days_diff in day_map: severe_days_indices.append(days_diff)
                            break # 避免重复添加

                # --- 构建动态标题 ---
                title = ""
                if severe_days_indices:
                    title = "⚠️ 今日天气-恶劣天气预警"
                elif rain_days_indices:
                    rain_days_set = set(rain_days_indices)
                    suffix = ""
                    if len(rain_days_set) == 3: suffix = "-未来三天有雨"
                    elif rain_days_set == {0, 1}: suffix = "-今明天有雨"
                    elif rain_days_set == {1, 2}: suffix = "-明后天有雨"
                    elif rain_days_set == {0, 2}: suffix = "-今后天有雨"
                    elif rain_days_set == {0}: suffix = "-今天有雨"
                    elif rain_days_set == {1}: suffix = "-明天有雨"
                    elif rain_days_set == {2}: suffix = "-后天有雨"
                    title = f"⚠️ 今日天气{suffix}"
                else:
                    title = "📢 今日天气"

                # --- 组合消息 ---
                header = f"📍 {self.location_name}\n"
                full_content = f"{header}\n{daily_content}"

                # 附加恶劣天气提醒
                if other_severe_alerts:
                    full_content += f"\n\n---\n**恶劣天气提醒**  \n" + "\n".join(other_severe_alerts)
                
                # 附加降雨提醒
                if rain_alerts:
                    full_content += f"\n\n---\n**降雨提醒**  \n" + "\n".join(rain_alerts)

                self.push_to_feishu(title, full_content)
                self.last_daily_push_date = today_str

    def _handle_rain_alert(self, now):
        """处理基于状态的降雨检查和预警逻辑（仅中雨及以上）。"""
        if now.minute % self.check_interval_minutes == 0:
            self.logger.info("检查未来6小时天气情况...")
            hourly_forecasts = self.get_hourly_weather()

            # 如果获取到了天气数据，就打印出来
            if hourly_forecasts:
                forecast_lines = [f"∙ {f['time']} | {f['text']} | 降水概率 {f['pop']}%") for f in hourly_forecasts]
                self.logger.info("未来6小时天气预报:\n" + "\n".join(forecast_lines))

            severe_rain_keywords = ["中雨", "大雨", "暴雨", "极端降雨"]
            detected_forecasts = []
            rain_start_time = None

            for item in hourly_forecasts:
                if any(keyword in item["text"] for keyword in severe_rain_keywords):
                    detected_forecasts.append(item)
                    if rain_start_time is None:
                        rain_start_time = item["time"]
            
            rain_detected = bool(detected_forecasts)

            if rain_detected:
                if not self.rain_active:
                    self.logger.info(f"检测到新的强降雨事件，预计在 {rain_start_time} 开始。准备推送预警。")
                    
                    title = f"⚠️ 预计 {rain_start_time} 有强降雨，请注意"
                    header = f"📍 {self.location_name}\n\n---\n"
                    hourly_lines = [f"∙ {f['time']} | {f['text']} | 降水概率 {f['pop']}%") for f in detected_forecasts]
                    hourly_content = "💧 **强降雨详情**  \n" + "  \n".join(hourly_lines)
                    
                    self.push_to_feishu(title, header + hourly_content)
                    self.rain_active = True
                else:
                    self.logger.info("强降雨持续中，不重复推送。")
            else:
                if self.rain_active:
                    self.logger.info("强降雨已过，重置降雨状态。下次将重新提醒。")
                else:
                    self.logger.info("未来6小时无强降雨风险，跳过推送。")
                self.rain_active = False

    def run_test_push(self):
        """发送一个包含所有元素的测试推送，用于检查格式。"""
        self.logger.info("发送测试推送...")
        
        daily_summary = ("📅 **今日天气 · 晴转多云**  \n" 
                         "🌡 气温：22 ~ 34℃  \n" 
                         "💨 风力：南风 4级  \n" 
                         "💧 湿度：80%")

        rain_warning = ("⚠️ **降雨预警 · 预计 15:00 开始**  \n" 
                        "∙ 15:00 | 小雨 | 概率 70%  \n" 
                        "∙ 16:00 | 中雨 | 概率 90%  \n" 
                        "∙ 17:00 | 小雨 | 概率 60%")

        header = f"📍 {self.location_name}\n"
        content = f"{header}\n{daily_summary}\n\n---\n{rain_warning}"
        title = "📢【测试】天气及降雨提醒"

        self.push_to_feishu(title, content)
        self.logger.info("测试推送发送完成。")

    def run(self):
        """天气监控的主循环。"""
        self.logger.info("脚本启动，进入主循环...")
        while True:
            now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))
            
            self._handle_daily_push(now)
            self._handle_rain_alert(now)

            # 计算并休眠到下一个检查时间点
            next_minute = (self.check_interval_minutes - (now.minute % self.check_interval_minutes)) % self.check_interval_minutes
            if next_minute == 0:
                next_minute = self.check_interval_minutes
            sleep_seconds = next_minute * 60 - now.second
            self.logger.info(f"等待 {sleep_seconds:.0f} 秒后进行下一次检查...")
            time.sleep(sleep_seconds)

def main():
    """
    脚本入口点。
    创建 WeatherMonitor 实例并根据参数运行。
    --test: 发送一条测试通知并退出。
    (无参数): 进入正常的监控循环。
    """
    setup_logging() # 初始化日志
    
    # 将重启逻辑移入main函数，以便更好地控制
    while True:
        try:
            monitor = WeatherMonitor()
            if len(sys.argv) > 1 and sys.argv[1] == '--test':
                monitor.run_test_push()
                break # 测试模式下运行一次后退出
            else:
                monitor.run()
        except configparser.Error as e:
            logging.critical(f"致命错误：无法读取或解析 config.ini: {e}")
            break # 如果配置文件损坏，则退出
        except Exception as e:
            # 在常规模式下才重启
            if not (len(sys.argv) > 1 and sys.argv[1] == '--test'):
                 logging.critical(f"主程序崩溃: {e}。5秒后将自动重启...", exc_info=True)
                 time.sleep(5)
            else:
                 logging.error(f"测试推送时发生错误: {e}", exc_info=True)
                 break # 测试模式下出错也退出

if __name__ == "__main__":
    main()