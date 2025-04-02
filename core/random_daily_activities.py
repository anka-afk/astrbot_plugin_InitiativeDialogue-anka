# Description: 随机日常模块，在指定时间段发送不同类型的日常消息

import asyncio
import datetime
import logging
from typing import Dict, Any, Set

from ..utils.message_manager import MessageManager
from ..utils.user_manager import UserManager
from ..utils.task_manager import TaskManager
from ..utils.config_manager import ConfigManager

# 配置日志
logger = logging.getLogger("random_daily_activities")


class RandomDailyActivities:
    """随机日常类，负责在特定时间段发送不同类型的日常消息"""

    def __init__(self, parent):
        """初始化随机日常模块

        Args:
            parent: 父插件实例，用于访问上下文和配置
        """
        self.parent = parent

        # 加载配置
        self.config_manager = ConfigManager(parent.config)
        module_config = self.config_manager.get_module_config("random_daily_activities")

        # 功能总开关
        self.enabled = module_config.get("enabled", True)

        # 午餐时间配置
        lunch_config = module_config.get("lunch_time", {})
        self.lunch_enabled = lunch_config.get("enabled", True)
        self.lunch_start_hour = lunch_config.get("start_hour", 11)
        self.lunch_end_hour = lunch_config.get("end_hour", 13)

        # 晚餐时间配置
        dinner_config = module_config.get("dinner_time", {})
        self.dinner_enabled = dinner_config.get("enabled", True)
        self.dinner_start_hour = dinner_config.get("start_hour", 17)
        self.dinner_end_hour = dinner_config.get("end_hour", 19)

        # 日常分享配置
        sharing_config = module_config.get("daily_sharing", {})
        self.sharing_enabled = sharing_config.get("enabled", True)
        self.min_interval_minutes = sharing_config.get("min_interval_minutes", 180)
        self.max_interval_minutes = sharing_config.get("max_interval_minutes", 360)

        # 使用共享的提示词列表
        self.lunch_prompts = [
            "请以自然的语气，简短地询问用户吃午饭了吗，可以稍微表达自己的饥饿感",
            "请以亲切的语气，简短地询问用户中午想吃什么，并分享一下你的午餐选择",
            "请以活泼的语气，简短地邀请用户一起吃午饭，可以提议一些美食选择",
            "请以随意的语气，简短地向用户抱怨一下你还没吃午饭，肚子有点饿了",
            "请以友好的语气，简短地询问用户是否需要你推荐一些午餐选择",
        ]

        self.dinner_prompts = [
            "请以温和的语气，简短地询问用户晚餐打算吃什么，可以提一下你自己的想法",
            "请以轻松的语气，简短地邀请用户一起享用晚餐，可以询问用户喜欢什么口味",
            "请以惬意的语气，简短地和用户聊聊晚餐，分享你喜欢的一道晚餐菜品",
            "请以关心的语气，简短地提醒用户该吃晚饭了，可以询问用户是否已经吃过",
            "请以好奇的语气，简短地询问用户晚餐有什么安排，可以表达一点期待感",
        ]

        # 按时间段的日常分享提示词
        self.time_period_prompts = {
            "早上": [
                "请简短描述你早上刚起床时的一个日常行为或想法，内容要符合当前时间(上午)，语气要自然随意",
                "请简短分享你早上看到的一个有趣事物或现象，内容要符合当前时间(上午)，语气要轻松活泼",
                "请简短描述你早上的一个小计划或安排，内容要符合当前时间(上午)，语气要积极向上",
            ],
            "下午": [
                "请简短描述你下午做的一个休闲活动，内容要符合当前时间(下午)，语气要轻松愉快",
                "请简短分享你下午看到或遇到的一个小趣事，内容要符合当前时间(下午)，语气要生动有趣",
                "请简短描述你下午的一个小感悟或想法，内容要符合当前时间(下午)，语气要自然平和",
            ],
            "晚上": [
                "请简短描述你晚上的一个放松方式，内容要符合当前时间(晚上)，语气要舒适惬意",
                "请简短分享你晚上看到的一个温馨或美好的场景，内容要符合当前时间(晚上)，语气要柔和",
                "请简短描述你晚上的一个小习惯或仪式感行为，内容要符合当前时间(晚上)，语气要亲切",
            ],
            "深夜": [
                "请简短描述你深夜的一个安静时刻或思考，内容要符合当前时间(深夜)，语气要轻柔",
                "请简短分享你深夜喜欢做的一件小事，内容要符合当前时间(深夜)，语气要intimate",
                "请简短描述你深夜的一个小心愿或期待，内容要符合当前时间(深夜)，语气要温暖",
            ],
        }

        # 跟踪用户今日已收到的消息
        self.today_lunch_users = set()
        self.today_dinner_users = set()
        self.last_sharing_time = {}  # 用户ID -> 上次分享时间

        # 记录最近一次检查的日期，用于重置状态
        self.last_check_date = datetime.datetime.now().date()

        # 主要任务引用
        self.daily_task = None

        # 初始化共享组件
        self.message_manager = MessageManager(parent)
        self.user_manager = UserManager(parent)
        self.task_manager = TaskManager(parent)

        logger.info(
            f"随机日常模块初始化完成，状态：{'启用' if self.enabled else '禁用'}"
        )

    async def start(self):
        """启动随机日常任务"""
        if not self.enabled:
            logger.info("随机日常功能已禁用，不启动任务")
            return

        if self.daily_task is not None:
            logger.warning("随机日常任务已经在运行中")
            return

        logger.info("启动随机日常任务")
        self.daily_task = asyncio.create_task(self._daily_check_loop())

    async def stop(self):
        """停止随机日常任务"""
        if self.daily_task is not None and not self.daily_task.done():
            self.daily_task.cancel()
            logger.info("随机日常任务已停止")
            self.daily_task = None

    async def _daily_check_loop(self):
        """定时检查是否需要发送随机日常消息的循环"""
        try:
            while True:
                # 检查当前时间
                now = datetime.datetime.now()
                current_date = now.date()
                current_hour = now.hour

                # 如果日期变了，重置状态
                if current_date != self.last_check_date:
                    logger.info(f"日期已变更为 {current_date}，重置随机日常状态")
                    self.today_lunch_users.clear()
                    self.today_dinner_users.clear()
                    self.last_check_date = current_date

                # 1. 检查是否在午餐时间段
                if (
                    self.lunch_enabled
                    and self.lunch_start_hour <= current_hour < self.lunch_end_hour
                ):
                    await self._check_meal_time("lunch")

                # 2. 检查是否在晚餐时间段
                if (
                    self.dinner_enabled
                    and self.dinner_start_hour <= current_hour < self.dinner_end_hour
                ):
                    await self._check_meal_time("dinner")

                # 3. 检查是否需要发送日常分享
                if self.sharing_enabled:
                    await self._check_daily_sharing()

                # 每10s检查一次
                await asyncio.sleep(10)

        except asyncio.CancelledError:
            logger.info("随机日常检查循环已取消")
            raise
        except Exception as e:
            logger.error(f"随机日常检查循环发生错误: {str(e)}")

    async def _check_meal_time(self, meal_type: str):
        """检查是否需要发送用餐相关消息

        Args:
            meal_type: 用餐类型，"lunch" 或 "dinner"
        """
        try:
            # 确定使用哪个已发送集合和提示词
            users_set = (
                self.today_lunch_users
                if meal_type == "lunch"
                else self.today_dinner_users
            )
            prompts = (
                self.lunch_prompts if meal_type == "lunch" else self.dinner_prompts
            )
            meal_name = "午餐" if meal_type == "lunch" else "晚餐"

            # 获取所有符合条件的用户
            eligible_users = self.user_manager.get_eligible_users(users_set)

            if not eligible_users:
                return

            # 随机选择一些用户发送消息
            selected_users = self.user_manager.select_random_users(
                eligible_users, 0.3, 1
            )

            for user_id, record in selected_users:
                # 创建异步任务发送用餐消息
                task_id = (
                    f"{meal_type}_{user_id}_{int(datetime.datetime.now().timestamp())}"
                )

                # 使用任务管理器调度任务
                await self.task_manager.schedule_task(
                    task_id=task_id,
                    coroutine_func=self._send_scheduled_message,
                    random_delay=True,
                    min_delay=1,
                    max_delay=30,
                    user_id=user_id,
                    conversation_id=record["conversation_id"],
                    unified_msg_origin=record["unified_msg_origin"],
                    message_type=meal_name,
                    prompts=prompts,
                )

                # 将用户添加到今日已发送集合
                users_set.add(user_id)

        except Exception as e:
            logger.error(f"检查{meal_type}时间任务时发生错误: {str(e)}")

    async def _check_daily_sharing(self):
        """检查是否需要发送日常分享消息"""
        try:
            now = datetime.datetime.now()

            # 获取当前时间段名称
            current_hour = now.hour
            if 5 <= current_hour < 12:
                time_period = "早上"
            elif 12 <= current_hour < 18:
                time_period = "下午"
            elif 18 <= current_hour < 23:
                time_period = "晚上"
            else:
                time_period = "深夜"

            # 遍历每个用户，检查是否符合条件
            # 获取所有符合条件的用户
            eligible_users = []

            # 检查现有用户记录
            for user_id, record in list(self.parent.dialogue_core.user_records.items()):
                # 检查是否在白名单中
                if not self.user_manager.is_user_in_whitelist(user_id):
                    continue

                # 检查最后分享时间
                last_time = self.last_sharing_time.get(user_id)
                if last_time:
                    minutes_since_last = (now - last_time).total_seconds() / 60
                    if minutes_since_last < self.min_interval_minutes:
                        # 未达到最小间隔，跳过
                        continue

                # 符合条件的用户
                eligible_users.append((user_id, record))

            if not eligible_users:
                return

            # 遍历用户，随机决定是否发送分享消息
            for user_id, record in eligible_users:
                # 计算发送概率 - 基于上次发送时间的间隔
                last_time = self.last_sharing_time.get(user_id)

                if last_time:
                    minutes_since_last = (now - last_time).total_seconds() / 60
                    # 线性增加概率，从最小间隔时的0%到最大间隔时的80%
                    if minutes_since_last >= self.max_interval_minutes:
                        probability = 0.8  # 80%概率
                    else:
                        # 线性插值计算概率
                        ratio = (minutes_since_last - self.min_interval_minutes) / (
                            self.max_interval_minutes - self.min_interval_minutes
                        )
                        probability = ratio * 0.8  # 最高80%概率
                else:
                    # 首次分享，50%概率
                    probability = 0.5

                # 根据概率决定是否发送
                import random

                if random.random() <= probability:
                    # 决定发送，为用户安排10分钟内随机时间发送消息
                    prompts = self.time_period_prompts.get(time_period, [])
                    if not prompts:
                        continue

                    # 创建异步任务发送日常分享消息
                    task_id = f"sharing_{user_id}_{int(now.timestamp())}"

                    # 使用任务管理器调度任务
                    await self.task_manager.schedule_task(
                        task_id=task_id,
                        coroutine_func=self._send_scheduled_message,
                        random_delay=True,
                        min_delay=1,
                        max_delay=10,
                        user_id=user_id,
                        conversation_id=record["conversation_id"],
                        unified_msg_origin=record["unified_msg_origin"],
                        message_type=f"{time_period}日常分享",
                        prompts=prompts,
                        time_period=time_period,
                    )

                    # 更新最后分享时间
                    self.last_sharing_time[user_id] = now

        except Exception as e:
            logger.error(f"检查日常分享任务时发生错误: {str(e)}")

    async def _send_scheduled_message(
        self,
        user_id,
        conversation_id,
        unified_msg_origin,
        message_type,
        prompts,
        time_period=None,
    ):
        """发送计划的消息

        Args:
            user_id: 用户ID
            conversation_id: 会话ID
            unified_msg_origin: 统一消息来源
            message_type: 消息类型描述
            prompts: 提示词列表
            time_period: 可选的时间段描述
        """
        # 再次检查用户是否在白名单中
        if not self.user_manager.is_user_in_whitelist(user_id):
            logger.info(f"用户 {user_id} 不再在白名单中，取消发送{message_type}消息")
            return

        # 使用消息管理器发送消息
        await self.message_manager.generate_and_send_message(
            user_id=user_id,
            conversation_id=conversation_id,
            unified_msg_origin=unified_msg_origin,
            prompts=prompts,
            message_type=message_type,
            time_period=time_period,
        )
