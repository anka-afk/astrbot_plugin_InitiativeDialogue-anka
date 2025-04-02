# Description: 一个主动对话插件，当用户长时间不回复时主动发送消息
from astrbot.api.provider import ProviderRequest
from astrbot.api.star import Context, register, Star
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api import AstrBotConfig, logger
import asyncio
import os
import pathlib
from .core.daily_greetings import DailyGreetings
from .core.initiative_dialogue_core import InitiativeDialogueCore
from .core.random_daily_activities import RandomDailyActivities
from .utils.data_loader import DataLoader


@register(
    "initiative_dialogue",
    "Jason",
    "主动对话, 当用户长时间不回复时主动发送消息",
    "1.0.0",
)
class InitiativeDialogue(Star):
    def __init__(self, context: Context, config: AstrBotConfig = None):
        super().__init__(context)
        # 基础配置
        self.config = config or {}

        # 设置数据存储路径
        self.data_dir = (
            pathlib.Path(os.path.dirname(os.path.abspath(__file__))) / "data"
        )
        self.data_file = self.data_dir / "umo_storage.json"

        # 确保数据目录存在
        self.data_dir.mkdir(exist_ok=True)

        # 初始化核心对话模块
        self.dialogue_core = InitiativeDialogueCore(self, self)

        # 初始化定时问候模块
        self.daily_greetings = DailyGreetings(self)

        # 初始化随机日常模块
        self.random_daily = RandomDailyActivities(self)

        # 初始化数据加载器并加载数据
        self.data_loader = DataLoader.get_instance(self)
        self.data_loader.load_data_from_storage()

        # 记录配置信息到日志
        logger.info(
            f"已加载配置，不活跃时间阈值: {self.dialogue_core.inactive_time_seconds}秒, "
            f"随机回复窗口: {self.dialogue_core.max_response_delay_seconds}秒, "
            f"时间限制: {'启用' if self.dialogue_core.time_limit_enabled else '禁用'}, "
            f"活动时间: {self.dialogue_core.activity_start_hour}点-{self.dialogue_core.activity_end_hour}点"
        )
        logger.info(
            f"白名单功能状态: {'启用' if self.dialogue_core.whitelist_enabled else '禁用'}, "
            f"白名单用户数量: {len(self.dialogue_core.whitelist_users)}"
        )

        # 启动检查任务
        asyncio.create_task(self.dialogue_core.start_checking_inactive_conversations())

        # 启动定期保存数据任务
        asyncio.create_task(self.data_loader.start_periodic_save())

        # 启动定时问候任务
        asyncio.create_task(self.daily_greetings.start())

        # 启动随机日常任务
        asyncio.create_task(self.random_daily.start())

        logger.info("主动对话插件初始化完成，检测任务已启动")

    @filter.event_message_type(filter.EventMessageType.PRIVATE_MESSAGE)
    async def on_private_message(self, event: AstrMessageEvent):
        """处理私聊消息"""
        user_id = str(event.get_sender_id())
        # 委托给核心模块处理
        await self.dialogue_core.handle_user_message(user_id, event)

    @filter.on_llm_request()
    async def check_initiative_response(self, event, req: ProviderRequest):
        """检查是否是对主动消息的回复，并修改提示词"""
        if event is None:
            return

        try:
            user_id = str(event.get_sender_id())
            # 委托给核心模块处理请求修改
            self.dialogue_core.modify_llm_request_for_initiative_response(user_id, event, req)

        except Exception as e:
            logger.error(f"[钩子错误] 处理用户回复主动消息时出错: {str(e)}")

    async def terminate(self):
        """插件被卸载/停用时调用"""
        logger.info("正在停止主动对话插件...")

        # 保存当前数据
        self.data_loader.save_data_to_storage()

        # 停止核心模块的检查任务
        await self.dialogue_core.stop_checking_inactive_conversations()

        # 停止定期保存数据的任务
        await self.data_loader.stop_periodic_save()

        # 停止定时问候任务
        await self.daily_greetings.stop()

        # 停止随机日常任务
        await self.random_daily.stop()

    @filter.command("initiative_test_message")
    async def test_initiative_message(self, event: AstrMessageEvent):
        """测试主动消息生成"""
        if not event.is_admin():
            yield event.plain_result("只有管理员可以使用此命令")
            return
            
        user_id = str(event.get_sender_id())
        conversation_id =  await self.context.conversation_manager.get_curr_conversation_id(event.unified_msg_origin)
        unified_msg_origin = event.unified_msg_origin
        
        yield event.plain_result("正在生成测试消息...")
        
        prompts = self.dialogue_core.initiative_prompts
        time_period = "测试"
        
        test_message = await self.dialogue_core.message_manager.generate_and_send_message(
            user_id = user_id,
            conversation_id=conversation_id,
            unified_msg_origin=unified_msg_origin,
            prompts=prompts,
            message_type="早上",
            time_period=time_period
        )
        
        if test_message:
            yield event.plain_result(f"测试消息生成成功:\n\n{test_message}")
        else:
            yield event.plain_result("测试消息生成失败")