# Description: 每日问候模块，在特定时间段向用户发送问候消息

import asyncio
import datetime
import logging
import random
from typing import Dict, Any, Set, List

from ..utils.message_manager import MessageManager
from ..utils.user_manager import UserManager
from ..utils.task_manager import TaskManager
from ..utils.config_manager import ConfigManager

# 配置日志
logger = logging.getLogger("daily_greetings")


class DailyGreetings:
    """每日问候类，负责在特定时间发送问候消息"""

    def __init__(self, parent):
        """初始化每日问候模块

        Args:
            parent: 父插件实例，用于访问上下文和配置
        """
        self.parent = parent

        # 加载配置
        self.config_manager = ConfigManager(parent.config)
        module_config = self.config_manager.get_module_config("daily_greetings")

        # 功能总开关
        self.enabled = module_config.get("enabled", True)

        # 早晨问候配置
        morning_config = module_config.get("morning", {})
        self.morning_enabled = morning_config.get("enabled", True)
        self.morning_start_hour = morning_config.get("start_hour", 6)
        self.morning_end_hour = morning_config.get("end_hour", 9)

        # 晚安问候配置
        night_config = module_config.get("night", {})
        self.night_enabled = night_config.get("enabled", True)
        self.night_start_hour = night_config.get("start_hour", 22)
        self.night_end_hour = night_config.get("end_hour", 24)  # 24表示第二天的0点

        # 选择用户配置
        self.user_selection_ratio = module_config.get("user_selection_ratio", 0.4)
        self.min_selected_users = module_config.get("min_selected_users", 1)

        # 问候提示词列表
        self.morning_prompts = [
            "请以温暖的语气，简短地向用户说早安，可以提及今天是美好的一天",
            "请以活力的语气，简短地问候用户早上好，可以鼓励用户积极面对新的一天",
            "请以轻松的语气，简短地向用户道早安，可以提到早晨的美好景象",
            "请以愉快的语气，简短地与用户分享早安祝福，可以表达对用户的关心",
            "请以亲切的语气，简短地给用户发送早安问候，可以提及希望用户有个美好的一天",
        ]

        self.night_prompts = [
            "请以温柔的语气，简短地向用户道晚安，可以提醒用户早点休息",
            "请以关心的语气，简短地与用户道晚安，可以询问用户今天过得如何",
            "请以平静的语气，简短地向用户说晚安，可以提及睡眠的重要性",
            "请以轻声的语气，简短地祝用户晚安，可以提到明天会更好",
            "请以舒适的语气，简短地向用户道晚安，可以表达希望用户做个好梦",
        ]

        # 跟踪用户今日已收到的问候
        self.today_morning_users = set()
        self.today_night_users = set()

        # 记录最近一次检查的日期，用于重置状态
        self.last_check_date = datetime.datetime.now().date()

        # 主要任务引用
        self.greeting_task = None

        # 初始化共享组件
        self.message_manager = MessageManager(parent)
        self.user_manager = UserManager(parent)
        self.task_manager = TaskManager(parent)

        logger.info(
            f"每日问候模块初始化完成，状态：{'启用' if self.enabled else '禁用'}"
        )

    async def start(self):
        """启动每日问候任务"""
        if not self.enabled:
            logger.info("每日问候功能已禁用，不启动任务")
            return

        if self.greeting_task is not None:
            logger.warning("每日问候任务已经在运行中")
            return

        logger.info("启动每日问候任务")
        self.greeting_task = asyncio.create_task(self._greeting_check_loop())

    async def stop(self):
        """停止每日问候任务"""
        if self.greeting_task is not None and not self.greeting_task.done():
            self.greeting_task.cancel()
            logger.info("每日问候任务已停止")
            self.greeting_task = None

    async def _greeting_check_loop(self):
        """定时检查是否需要发送问候消息的循环"""
        try:
            while True:
                # 检查当前时间
                now = datetime.datetime.now()
                current_date = now.date()
                current_hour = now.hour

                # 如果日期变了，重置状态
                if current_date != self.last_check_date:
                    logger.info(f"日期已变更为 {current_date}，重置每日问候状态")
                    self.today_morning_users.clear()
                    self.today_night_users.clear()
                    self.last_check_date = current_date

                # 1. 检查是否在早晨问候时间段
                if (
                    self.morning_enabled
                    and self.morning_start_hour <= current_hour < self.morning_end_hour
                ):
                    await self._check_greeting_time("morning")

                # 2. 检查是否在晚安问候时间段
                night_end = self.night_end_hour
                if night_end == 24:
                    night_end = 0  # 处理跨日的情况

                if self.night_enabled:
                    if (
                        self.night_start_hour <= current_hour < 24
                        or 0 <= current_hour < night_end
                    ):
                        await self._check_greeting_time("night")

                # 每分钟检查一次
                await asyncio.sleep(60)

        except asyncio.CancelledError:
            logger.info("每日问候检查循环已取消")
            raise
        except Exception as e:
            logger.error(f"每日问候检查循环发生错误: {str(e)}")

    async def _check_greeting_time(self, greeting_type: str):
        """检查是否需要发送问候消息

        Args:
            greeting_type: 问候类型，"morning" 或 "night"
        """
        try:
            # 确定使用哪个已发送集合和提示词
            users_set = (
                self.today_morning_users
                if greeting_type == "morning"
                else self.today_night_users
            )
            prompts = (
                self.morning_prompts
                if greeting_type == "morning"
                else self.night_prompts
            )
            greeting_name = "早安" if greeting_type == "morning" else "晚安"

            # 获取所有符合条件的用户
            eligible_users = self.user_manager.get_eligible_users(users_set)

            if not eligible_users:
                return

            # 随机选择一些用户发送消息
            selected_users = self.user_manager.select_random_users(
                eligible_users, self.user_selection_ratio, self.min_selected_users
            )

            for user_id, record in selected_users:
                # 创建异步任务发送问候消息
                task_id = f"{greeting_type}_{user_id}_{int(datetime.datetime.now().timestamp())}"

                # 使用任务管理器调度任务
                await self.task_manager.schedule_task(
                    task_id=task_id,
                    coroutine_func=self._send_greeting_message,
                    random_delay=True,
                    min_delay=1,
                    max_delay=40,  # 更长的延迟时间，让消息分散发送
                    user_id=user_id,
                    conversation_id=record["conversation_id"],
                    unified_msg_origin=record["unified_msg_origin"],
                    greeting_type=greeting_name,
                    prompts=prompts,
                )

                # 将用户添加到今日已发送集合
                users_set.add(user_id)

        except Exception as e:
            logger.error(f"检查{greeting_type}问候任务时发生错误: {str(e)}")

    async def _send_greeting_message(
        self,
        user_id: str,
        conversation_id: str,
        unified_msg_origin: str,
        greeting_type: str,
        prompts: List[str],
    ):
        """发送问候消息

        Args:
            user_id: 用户ID
            conversation_id: 会话ID
            unified_msg_origin: 统一消息来源
            greeting_type: 问候类型描述
            prompts: 提示词列表
        """
        # 再次检查用户是否在白名单中
        if not self.user_manager.is_user_in_whitelist(user_id):
            logger.info(f"用户 {user_id} 不在白名单中，取消发送{greeting_type}消息")
            return

        # 确定当前时间段
        current_hour = datetime.datetime.now().hour
        if 5 <= current_hour < 12:
            time_period = "早上"
        elif 12 <= current_hour < 18:
            time_period = "下午"
        elif 18 <= current_hour < 22:
            time_period = "晚上"
        else:
            time_period = "深夜"

        # 使用消息管理器发送消息
        await self.message_manager.generate_and_send_message(
            user_id=user_id,
            conversation_id=conversation_id,
            unified_msg_origin=unified_msg_origin,
            prompts=prompts,
            message_type=greeting_type,
            time_period=time_period,
        )
