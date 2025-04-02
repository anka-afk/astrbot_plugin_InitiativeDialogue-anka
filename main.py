# Description: 一个主动对话插件，当用户长时间不回复时主动发送消息
from astrbot.api.all import *
from astrbot.api.event import filter  # 明确导入对象
from astrbot.api.provider import ProviderRequest  # 添加导入
import datetime
import asyncio
import json
import os
import pathlib
import sys
from typing import Dict, Any

# 修改导入语句，确保能找到相关模块
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

from daily_greetings import DailyGreetings
from initiative_dialogue_core import InitiativeDialogueCore
from random_daily_activities import RandomDailyActivities  # 导入新模块

@register("initiative_dialogue", "Jason","主动对话, 当用户长时间不回复时主动发送消息", "1.0.0")
class InitiativeDialogue(Star):
    def __init__(self, context: Context, config: AstrBotConfig = None):
        super().__init__(context)
        # 基础配置
        self.config = config or {}
        
        # 设置数据存储路径
        self.data_dir = pathlib.Path(os.path.dirname(os.path.abspath(__file__))) / "data"
        self.data_file = self.data_dir / "umo_storage.json"
        
        # 确保数据目录存在
        self.data_dir.mkdir(exist_ok=True)
        
        # 初始化核心对话模块
        self.dialogue_core = InitiativeDialogueCore(self)
        
        # 初始化定时问候模块
        self.daily_greetings = DailyGreetings(self)
        
        # 初始化随机日常模块
        self.random_daily = RandomDailyActivities(self)
        
        # 从本地存储加载数据
        self._load_data_from_storage()
        
        # 记录配置信息到日志
        logger.info(f"已加载配置，不活跃时间阈值: {self.dialogue_core.inactive_time_seconds}秒, "
                    f"随机回复窗口: {self.dialogue_core.max_response_delay_seconds}秒, "
                    f"时间限制: {'启用' if self.dialogue_core.time_limit_enabled else '禁用'}, "
                    f"活动时间: {self.dialogue_core.activity_start_hour}点-{self.dialogue_core.activity_end_hour}点")
        logger.info(f"白名单功能状态: {'启用' if self.dialogue_core.whitelist_enabled else '禁用'}, "
                    f"白名单用户数量: {len(self.dialogue_core.whitelist_users)}")
                
        # 启动检查任务
        asyncio.create_task(self.dialogue_core.start_checking_inactive_conversations())
        
        # 定期保存数据的任务
        self.save_data_task = asyncio.create_task(self._periodic_save_data())
        
        # 启动定时问候任务
        asyncio.create_task(self.daily_greetings.start())
        
        # 启动随机日常任务
        asyncio.create_task(self.random_daily.start())
        
        logger.info("主动对话插件初始化完成，检测任务已启动")
    
    def _load_data_from_storage(self) -> None:
        """从本地存储加载数据"""
        try:
            if self.data_file.exists():
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    stored_data = json.load(f)
                    
                    # 加载用户记录
                    if 'user_records' in stored_data:
                        # 转换时间戳字符串为datetime对象
                        for user_id, record in stored_data['user_records'].items():
                            if 'timestamp' in record and isinstance(record['timestamp'], str):
                                try:
                                    record['timestamp'] = datetime.datetime.fromisoformat(record['timestamp'])
                                except ValueError:
                                    # 如果时间戳格式无效，使用当前时间
                                    record['timestamp'] = datetime.datetime.now()
                        
                    # 加载最后主动消息记录
                    if 'last_initiative_messages' in stored_data:
                        # 转换时间戳字符串为datetime对象
                        for user_id, record in stored_data['last_initiative_messages'].items():
                            if 'timestamp' in record and isinstance(record['timestamp'], str):
                                try:
                                    record['timestamp'] = datetime.datetime.fromisoformat(record['timestamp'])
                                except ValueError:
                                    # 如果时间戳格式无效，使用当前时间
                                    record['timestamp'] = datetime.datetime.now()
                    
                    # 设置核心模块数据
                    self.dialogue_core.set_data(
                        user_records=stored_data.get('user_records', {}),
                        last_initiative_messages=stored_data.get('last_initiative_messages', {}),
                        users_received_initiative=set(stored_data.get('users_received_initiative', []))
                    )
                    
                logger.info(f"成功从 {self.data_file} 加载用户数据")
        except Exception as e:
            logger.error(f"从存储加载数据时发生错误: {str(e)}")
    
    def _save_data_to_storage(self) -> None:
        """将数据保存到本地存储"""
        try:
            # 从核心获取数据
            core_data = self.dialogue_core.get_data()
            
            # 创建要保存的数据结构
            data_to_save = {
                'user_records': self._prepare_records_for_save(core_data.get('user_records', {})),
                'last_initiative_messages': self._prepare_records_for_save(core_data.get('last_initiative_messages', {})),
                'users_received_initiative': list(core_data.get('users_received_initiative', []))
            }
            
            # 保存到文件
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump(data_to_save, f, ensure_ascii=False, indent=2)
                
            logger.info(f"数据已保存到 {self.data_file}")
        except Exception as e:
            logger.error(f"保存数据到存储时发生错误: {str(e)}")
    
    def _prepare_records_for_save(self, records: Dict[str, Any]) -> Dict[str, Any]:
        """准备记录以便保存，将datetime对象转换为ISO格式字符串"""
        prepared_records = {}
        
        for user_id, record in records.items():
            # 复制记录以避免修改原始数据
            record_copy = dict(record)
            
            # 转换timestamp字段
            if 'timestamp' in record_copy and isinstance(record_copy['timestamp'], datetime.datetime):
                record_copy['timestamp'] = record_copy['timestamp'].isoformat()
                
            prepared_records[user_id] = record_copy
            
        return prepared_records
    
    async def _periodic_save_data(self) -> None:
        """定期保存数据的异步任务"""
        try:
            while True:
                # 每5分钟保存一次数据
                await asyncio.sleep(300)
                self._save_data_to_storage()
        except asyncio.CancelledError:
            # 任务被取消时也保存一次数据
            self._save_data_to_storage()
            logger.info("定期保存数据任务已取消")
        except Exception as e:
            logger.error(f"定期保存数据任务发生错误: {str(e)}")
    
    @event_message_type(EventMessageType.PRIVATE_MESSAGE)
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
            self.dialogue_core.modify_llm_request_for_initiative_response(user_id, req)
                
        except Exception as e:
            logger.error(f"[钩子错误] 处理用户回复主动消息时出错: {str(e)}")

    async def terminate(self):
        '''插件被卸载/停用时调用'''
        logger.info("正在停止主动对话插件...")
        
        # 保存当前数据
        self._save_data_to_storage()
        
        # 停止核心模块的检查任务
        await self.dialogue_core.stop_checking_inactive_conversations()
        
        # 取消定期保存数据的任务
        if hasattr(self, 'save_data_task'):
            self.save_data_task.cancel()
            logger.info("已取消数据保存任务")
            
        # 停止定时问候任务
        await self.daily_greetings.stop()
        
        # 停止随机日常任务
        await self.random_daily.stop()