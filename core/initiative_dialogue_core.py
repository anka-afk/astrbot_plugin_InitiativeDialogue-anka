# Description: 主动对话核心模块，检测用户不活跃状态并发送主动消息

import asyncio
import datetime
import logging
import random
from typing import Dict, Any, Set, List, Optional

from astrbot.api.event import AstrMessageEvent
from astrbot.api.provider import ProviderRequest

from ..utils.message_manager import MessageManager
from ..utils.user_manager import UserManager
from ..utils.task_manager import TaskManager
from ..utils.config_manager import ConfigManager

# 配置日志
logger = logging.getLogger("initiative_dialogue_core")


class InitiativeDialogueCore:
    """主动对话核心类，管理用户状态并在适当时候发送主动消息"""

    def __init__(self, parent, star):
        """初始化主动对话核心

        Args:
            parent: 父插件实例，用于访问上下文和配置
        """
        self.parent = parent
        self.star = star
        self.context = star.context

        # 加载配置
        self.config_manager = ConfigManager(parent.config)
        core_config = self.config_manager.get_module_config("initiative_dialogue_core")

        # 核心配置参数
        self.inactive_time_seconds = core_config.get(
            "inactive_time_seconds", 3600
        )  # 默认1小时
        self.max_response_delay_seconds = core_config.get(
            "max_response_delay_seconds", 300
        )  # 默认5分钟
        self.time_limit_enabled = core_config.get("time_limit_enabled", True)
        self.activity_start_hour = core_config.get("activity_start_hour", 8)
        self.activity_end_hour = core_config.get("activity_end_hour", 22)

        # 白名单配置
        whitelist_config = core_config.get("whitelist", {})
        self.whitelist_enabled = whitelist_config.get("enabled", False)
        self.whitelist_users = set(whitelist_config.get("users", []))

        # 提示词配置
        self.initiative_prompts = core_config.get(
            "initiative_prompts",
            [
                "请以自然的语气，生成一条简短的主动消息，询问用户最近在做什么",
                "请以温和的语气，生成一条短小的主动问候，表达想念用户的心情",
                "请以随意的语气，生成一条简短的日常分享，可以提及你最近的'心情'或'想法'",
                "请以好奇的语气，生成一条简短的问题，询问用户对某个话题的看法",
            ],
        )

        # 回复检测配置
        self.initiative_response_keywords = core_config.get(
            "initiative_response_keywords",
            [
                "你好",
                "嗨",
                "在吗",
                "打扰",
                "抱歉",
                "最近",
                "怎么样",
                "好久不见",
                "想你",
            ],
        )

        # 用户数据
        self.user_records = (
            {}
        )  # user_id -> {"timestamp": datetime, "conversation_id": str, "unified_msg_origin": str}
        self.last_initiative_messages = (
            {}
        )  # user_id -> {"timestamp": datetime, "conversation_id": str, "unified_msg_origin": str}
        self.users_received_initiative = set()  # 记录已接收过主动消息的用户ID

        # 检查任务引用
        self.inactive_check_task = None

        # 初始化共享组件
        self.message_manager = MessageManager(parent)
        self.user_manager = UserManager(parent)
        self.task_manager = TaskManager(parent)

        logger.info(
            f"主动对话核心初始化完成，不活跃时间阈值：{self.inactive_time_seconds}秒"
        )

    def get_data(self) -> Dict[str, Any]:
        """获取核心数据用于持久化

        Returns:
            Dict: 包含用户记录和主动消息记录的字典
        """
        return {
            "user_records": self.user_records,
            "last_initiative_messages": self.last_initiative_messages,
            "users_received_initiative": self.users_received_initiative,
        }

    def set_data(
        self,
        user_records: Dict[str, Any],
        last_initiative_messages: Dict[str, Any],
        users_received_initiative: Set[str],
    ) -> None:
        """设置核心数据，从持久化存储恢复

        Args:
            user_records: 用户记录字典
            last_initiative_messages: 最后主动消息记录字典
            users_received_initiative: 已接收主动消息的用户ID集合
        """
        self.user_records = user_records
        self.last_initiative_messages = last_initiative_messages
        self.users_received_initiative = users_received_initiative

        logger.info(
            f"已加载用户数据，共有 {len(user_records)} 条用户记录，"
            f"{len(last_initiative_messages)} 条主动消息记录，"
            f"{len(users_received_initiative)} 个用户已接收主动消息"
        )

    async def start_checking_inactive_conversations(self) -> None:
        """启动检查不活跃对话的任务"""
        if self.inactive_check_task is not None:
            logger.warning("检查不活跃对话任务已在运行中")
            return

        logger.info("启动检查不活跃对话任务")
        self.inactive_check_task = asyncio.create_task(
            self._check_inactive_conversations_loop()
        )

    async def stop_checking_inactive_conversations(self) -> None:
        """停止检查不活跃对话的任务"""
        if self.inactive_check_task is not None and not self.inactive_check_task.done():
            self.inactive_check_task.cancel()
            try:
                await self.inactive_check_task
            except asyncio.CancelledError:
                pass

            self.inactive_check_task = None
            logger.info("不活跃对话检查任务已停止")

    async def _check_inactive_conversations_loop(self) -> None:
        """定期检查不活跃对话的循环"""
        try:
            while True:
                # 每30秒检查一次
                await asyncio.sleep(30)

                # 如果启用了时间限制，检查当前是否在活动时间范围内
                if self.time_limit_enabled:
                    current_hour = datetime.datetime.now().hour
                    if not (
                        self.activity_start_hour
                        <= current_hour
                        < self.activity_end_hour
                    ):
                        # 不在活动时间范围内，跳过本次检查
                        continue

                # 获取当前时间
                now = datetime.datetime.now()

                # 遍历所有用户记录，检查不活跃状态
                for user_id, record in list(self.user_records.items()):
                    # 如果启用了白名单且用户不在白名单中，跳过
                    if self.whitelist_enabled and user_id not in self.whitelist_users:
                        continue

                    # 检查用户最后活跃时间
                    last_active = record.get("timestamp")
                    if not last_active:
                        continue

                    # 计算不活跃时间（秒）
                    inactive_seconds = (now - last_active).total_seconds()

                    # 如果超过阈值，考虑发送主动消息
                    if inactive_seconds >= self.inactive_time_seconds:
                        # 检查是否需要发送主动消息
                        if await self._should_send_initiative_message(user_id):
                            # 为用户创建发送主动消息的任务
                            task_id = f"initiative_{user_id}_{int(now.timestamp())}"

                            # 计算随机延迟时间，增加自然感
                            await self.task_manager.schedule_task(
                                task_id=task_id,
                                coroutine_func=self._send_initiative_message,
                                random_delay=True,
                                min_delay=0,
                                max_delay=int(self.max_response_delay_seconds / 60),
                                user_id=user_id,
                                conversation_id=record["conversation_id"],
                                unified_msg_origin=record["unified_msg_origin"],
                            )

        except asyncio.CancelledError:
            logger.info("不活跃对话检查循环已取消")
            raise
        except Exception as e:
            logger.error(f"检查不活跃对话时发生错误: {str(e)}")

    async def _should_send_initiative_message(self, user_id: str) -> bool:
        """判断是否应该向指定用户发送主动消息

        Args:
            user_id: 用户ID

        Returns:
            bool: 是否应该发送主动消息
        """
        # 检查用户最后一次收到主动消息的时间
        last_message = self.last_initiative_messages.get(user_id)

        if last_message:
            # 如果最近已经发送过主动消息，检查间隔时间
            last_time = last_message.get("timestamp")
            if last_time:
                # 计算距离上次发送的时间（小时）
                hours_since_last = (
                    datetime.datetime.now() - last_time
                ).total_seconds() / 3600

                # 根据距离上次发送的时间计算发送概率
                # 时间越长，概率越高：6小时内不发送，6-12小时30%概率，12-24小时60%概率，24小时以上90%概率
                if hours_since_last < 6:
                    return False
                elif hours_since_last < 12:
                    return random.random() < 0.3
                elif hours_since_last < 24:
                    return random.random() < 0.6
                else:
                    return random.random() < 0.9
        else:
            # 如果是首次发送主动消息，50%概率发送
            return random.random() < 0.5

    async def _send_initiative_message(
        self, user_id: str, conversation_id: str, unified_msg_origin: str
    ) -> None:
        """发送主动消息给指定用户

        Args:
            user_id: 用户ID
            conversation_id: 会话ID
            unified_msg_origin: 统一消息来源
        """
        # 再次检查用户是否在白名单中（如果启用了白名单）
        if self.whitelist_enabled and user_id not in self.whitelist_users:
            logger.info(f"用户 {user_id} 不在白名单中，取消发送主动消息")
            return

        # 获取当前时间段，用于调整消息内容
        current_hour = datetime.datetime.now().hour
        if 5 <= current_hour < 12:
            time_period = "早上"
        elif 12 <= current_hour < 18:
            time_period = "下午"
        elif 18 <= current_hour < 22:
            time_period = "晚上"
        else:
            time_period = "深夜"

        # 使用消息管理器发送主动消息
        success = await self.message_manager.generate_and_send_message(
            user_id=user_id,
            conversation_id=conversation_id,
            unified_msg_origin=unified_msg_origin,
            prompts=self.initiative_prompts,
            message_type="主动消息",
            time_period=time_period,
        )

        if success:
            # 更新主动消息记录
            now = datetime.datetime.now()
            self.last_initiative_messages[user_id] = {
                "timestamp": now,
                "conversation_id": conversation_id,
                "unified_msg_origin": unified_msg_origin,
            }

            # 标记用户已接收主动消息
            self.users_received_initiative.add(user_id)

            logger.info(f"已向用户 {user_id} 发送主动消息")

    async def handle_user_message(self, user_id: str, event: AstrMessageEvent) -> None:
        """处理用户消息，更新活跃状态

        Args:
            user_id: 用户ID
            event: 消息事件
        """
        # 获取会话信息
        conversation_id =  await self.context.conversation_manager.get_curr_conversation_id(event.unified_msg_origin)
        unified_msg_origin = event.unified_msg_origin

        # 更新用户记录
        now = datetime.datetime.now()
        self.user_records[user_id] = {
            "timestamp": now,
            "conversation_id": conversation_id,
            "unified_msg_origin": unified_msg_origin,
        }

        # 记录日志（仅在调试模式下）
        logger.debug(f"已更新用户 {user_id} 的活跃状态，最后活跃时间：{now}")

    def modify_llm_request_for_initiative_response(
        self,event:AstrMessageEvent, user_id: str, req: ProviderRequest
    ) -> None:
        """修改LLM请求以适应对主动消息的回复

        Args:
            user_id: 用户ID
            req: LLM请求对象
        """
        # 检查用户是否最近收到过主动消息
        if user_id not in self.users_received_initiative:
            return

        # 获取用户输入文本
        user_input = req.event.message_str
        if not user_input:
            return

        # 检查用户输入是否像是对主动消息的回复
        is_response = False
        for keyword in self.initiative_response_keywords:
            if keyword in user_input:
                is_response = True
                break

        # 如果感觉是回复，修改系统提示词以增强连续性
        if is_response:
            # 获取当前系统提示词
            current_system_prompt = req.system_prompt or ""

            # 添加额外的上下文信息
            additional_context = "用户的消息可能是对你之前主动发送的消息的回复。保持对话的连续性和自然性，表现出对话中你主动联系过用户的特点。"

            # 更新系统提示词
            if additional_context not in current_system_prompt:
                req.system_prompt = f"{current_system_prompt}\n\n{additional_context}"

            # 移除用户标记，表示已处理该回复
            self.users_received_initiative.discard(user_id)

            logger.debug(
                f"已识别用户 {user_id} 的消息为对主动消息的回复，已调整系统提示词"
            )
