# Description: 定时问候模块，支持每天固定时间发送早安和晚安消息

import asyncio
import datetime
import json
import logging
import random
from typing import Dict, Any, Set, Optional

# 配置日志
logger = logging.getLogger("daily_greetings")

class DailyGreetings:
    """定时问候类，负责在每天指定时间发送早安和晚安消息"""
    
    def __init__(self, parent):
        """初始化定时问候模块
        
        Args:
            parent: 父插件实例，用于访问上下文和配置
        """
        self.parent = parent
        self.context = parent.context
        
        # 从父插件配置中加载定时问候配置
        self.config = parent.config.get('daily_greetings', {})
        
        # 功能开关
        self.enabled = self.config.get('enabled', False)
        
        # 时间设置（默认早上8点和晚上23点）
        self.morning_hour = self.config.get('morning_hour', 8)
        self.morning_minute = self.config.get('morning_minute', 0)
        self.night_hour = self.config.get('night_hour', 23)
        self.night_minute = self.config.get('night_minute', 0)
        
        # 问候语提示词列表 - 直接在代码中设置，不再从配置加载
        self.morning_prompts = [
            "请以温暖阳光的语气，简短地向用户道早安，祝愿他今天过得愉快",
            "请以活力四射的语气，简短地向用户问候早安，表达见到用户的喜悦",
            "请以温柔的语气，简短地向用户道早安，询问他昨晚睡得好不好",
            "请以可爱的语气，简短地向用户道早安，给他带来美好的一天"
        ]
        
        self.night_prompts = [
            "请以温柔的语气，简短地向用户道晚安，祝愿他有个好梦",
            "请以贴心的语气，简短地向用户道晚安，提醒他早点休息",
            "请以安静的语气，简短地向用户道晚安，表达对他明天的期待",
            "请以轻声细语的感觉，简短地向用户道晚安，关心他今天是否疲惫"
        ]
        
        # 记录今天已经发送过消息的用户
        self.morning_greeted_users: Set[str] = set()
        self.night_greeted_users: Set[str] = set()
        
        # 记录最近一次检查的日期，用于重置已问候用户集合
        self.last_check_date = datetime.datetime.now().date()
        
        # 任务对象
        self.greeting_task = None
        
        # 早安消息的最大随机延迟（分钟）
        self.morning_max_delay = self.config.get('morning_max_delay', 30)
        # 晚安消息的最大随机延迟（分钟）
        self.night_max_delay = self.config.get('night_max_delay', 30)
        
        # 用于存储从历史记录中加载的用户
        self.historical_users = {}
        
        logger.info(f"定时问候模块初始化完成，状态：{'启用' if self.enabled else '禁用'}")
        logger.info(f"早安时间设置为 {self.morning_hour:02d}:{self.morning_minute:02d}")
        logger.info(f"晚安时间设置为 {self.night_hour:02d}:{self.night_minute:02d}")
        logger.info(f"早安问候语数量: {len(self.morning_prompts)}, 晚安问候语数量: {len(self.night_prompts)}")
    
    async def start(self):
        """启动定时问候任务"""
        if not self.enabled:
            logger.info("定时问候功能已禁用，不启动任务")
            return
            
        # 加载历史用户记录
        self._load_historical_users()
        logger.info(f"从历史记录加载了 {len(self.historical_users)} 个用户供早晚安问候使用")
            
        if self.greeting_task is not None:
            logger.warning("定时问候任务已经在运行中")
            return
            
        logger.info("启动定时问候任务")
        self.greeting_task = asyncio.create_task(self._greeting_check_loop())
    
    def _load_historical_users(self):
        """从父插件的历史记录中加载用户数据，确保每次启动都能向所有已知用户发送问候"""
        try:
            # 清空历史用户字典
            self.historical_users.clear()
            
            # 加载主动对话插件中的历史消息记录
            if hasattr(self.parent, 'last_initiative_messages') and self.parent.last_initiative_messages:
                for user_id, record in self.parent.last_initiative_messages.items():
                    if 'conversation_id' in record and 'unified_msg_origin' in record:
                        # 如果启用了白名单，检查用户是否在白名单中
                        if self.parent.whitelist_enabled and user_id not in self.parent.whitelist_users:
                            logger.info(f"用户 {user_id} 不在白名单中，跳过加载到历史用户")
                            continue
                            
                        self.historical_users[user_id] = {
                            'conversation_id': record['conversation_id'],
                            'unified_msg_origin': record['unified_msg_origin']
                        }
                        
            logger.info(f"成功从历史记录中加载了 {len(self.historical_users)} 个用户")
        except Exception as e:
            logger.error(f"从历史记录加载用户数据时出错: {str(e)}")

    async def stop(self):
        """停止定时问候任务"""
        if self.greeting_task is not None and not self.greeting_task.done():
            self.greeting_task.cancel()
            logger.info("定时问候任务已停止")
            self.greeting_task = None
    
    async def _greeting_check_loop(self):
        """定时检查是否需要发送问候消息的循环"""
        try:
            while True:
                # 检查当前时间
                now = datetime.datetime.now()
                current_date = now.date()
                current_hour = now.hour
                current_minute = now.minute
                
                # 如果日期变了，重置已问候用户集合
                if current_date != self.last_check_date:
                    logger.info(f"日期已变更为 {current_date}，重置已问候用户记录")
                    self.morning_greeted_users.clear()
                    self.night_greeted_users.clear()
                    self.last_check_date = current_date
                    
                    # 在新的一天重新加载历史用户
                    self._load_historical_users()
                    logger.info(f"新的一天已重新加载 {len(self.historical_users)} 个历史用户")
                
                # 检查是否到达发送早安消息的时间
                if (current_hour == self.morning_hour and current_minute == self.morning_minute and
                        (len(self.morning_greeted_users) < len(self.parent.user_records) + len(self.historical_users))):
                    logger.info("到达早安消息发送时间")
                    await self._schedule_greeting_messages("morning")
                
                # 检查是否到达发送晚安消息的时间
                if (current_hour == self.night_hour and current_minute == self.night_minute and
                        (len(self.night_greeted_users) < len(self.parent.user_records) + len(self.historical_users))):
                    logger.info("到达晚安消息发送时间")
                    await self._schedule_greeting_messages("night")
                
                # 每分钟检查一次
                await asyncio.sleep(60)
                
        except asyncio.CancelledError:
            logger.info("定时问候检查循环已取消")
        except Exception as e:
            logger.error(f"定时问候检查循环发生错误: {str(e)}")
    
    async def _schedule_greeting_messages(self, greeting_type: str):
        """为所有用户安排问候消息发送
        
        Args:
            greeting_type: 问候类型，"morning" 或 "night"
        """
        try:
            # 确定已问候用户集合和提示词列表
            if greeting_type == "morning":
                greeted_users = self.morning_greeted_users
                prompts = self.morning_prompts
                max_delay = self.morning_max_delay
                greeting_name = "早安"
            else:
                greeted_users = self.night_greeted_users
                prompts = self.night_prompts
                max_delay = self.night_max_delay
                greeting_name = "晚安"
            
            # 创建一个合并的用户列表 - 优先使用当前活跃用户
            combined_users = {}
            
            # 首先添加所有当前活跃用户
            for user_id, record in list(self.parent.user_records.items()):
                # 检查用户是否已经收到过今天的问候
                if user_id in greeted_users:
                    continue
                
                # 检查是否启用白名单，以及用户是否在白名单中
                if self.parent.whitelist_enabled and user_id not in self.parent.whitelist_users:
                    continue
                
                combined_users[user_id] = record
            
            # 然后添加历史用户（如果他们不在当前活跃用户中）
            for user_id, record in list(self.historical_users.items()):
                if user_id not in combined_users and user_id not in greeted_users:
                    # 再次检查白名单（以防白名单在启动后被修改）
                    if self.parent.whitelist_enabled and user_id not in self.parent.whitelist_users:
                        continue
                    
                    combined_users[user_id] = record
            
            # 现在遍历合并后的用户列表发送问候
            users_count = len(combined_users)
            if users_count > 0:
                logger.info(f"找到 {users_count} 个用户需要发送{greeting_name}消息")
            
            for user_id, record in combined_users.items():
                # 为每个用户安排一个随机延迟时间发送消息
                delay_minutes = random.randint(0, max_delay)
                
                # 创建异步任务发送问候
                task_id = f"greeting_{greeting_type}_{user_id}"
                task = asyncio.create_task(self._send_greeting_message(
                    user_id=user_id,
                    conversation_id=record['conversation_id'],
                    unified_msg_origin=record['unified_msg_origin'],
                    greeting_type=greeting_type,
                    delay_minutes=delay_minutes,
                    prompts=prompts
                ))
                
                # 存储任务以防被垃圾回收
                if not hasattr(self.parent, '_message_tasks'):
                    self.parent._message_tasks = {}
                    
                self.parent._message_tasks[task_id] = task
                
                # 设置清理回调
                def remove_task(t, tid=task_id):
                    if tid in self.parent._message_tasks:
                        self.parent._message_tasks.pop(tid, None)
                
                task.add_done_callback(remove_task)
                
                # 将用户添加到已问候集合中
                greeted_users.add(user_id)
                
                scheduled_time = datetime.datetime.now() + datetime.timedelta(minutes=delay_minutes)
                logger.info(f"为用户 {user_id} 安排在 {delay_minutes} 分钟后({scheduled_time.strftime('%H:%M')})发送{greeting_name}消息")
                
        except Exception as e:
            logger.error(f"安排{greeting_name}消息时发生错误: {str(e)}")
    
    async def _send_greeting_message(self, user_id: str, conversation_id: str, 
                                    unified_msg_origin: dict, greeting_type: str, 
                                    delay_minutes: int, prompts: list):
        """发送问候消息
        
        Args:
            user_id: 用户ID
            conversation_id: 会话ID
            unified_msg_origin: 统一消息来源
            greeting_type: 问候类型，"morning" 或 "night"
            delay_minutes: 延迟发送的分钟数
            prompts: 可用的提示词列表
        """
        try:
            # 等待指定的延迟时间
            await asyncio.sleep(delay_minutes * 60)
            
            # 再次检查用户是否在白名单中（针对延迟期间可能发生的白名单变化）
            if self.parent.whitelist_enabled and user_id not in self.parent.whitelist_users:
                logger.info(f"用户 {user_id} 不再在白名单中，取消发送问候消息")
                return
                
            # 获取对话对象
            conversation = await self.context.conversation_manager.get_conversation(unified_msg_origin, conversation_id)
            
            if not conversation:
                logger.error(f"无法获取用户 {user_id} 的对话，会话ID: {conversation_id} 可能不存在")
                return
                
            context = []
            system_prompt = "你是一个可爱的AI助手，喜欢和用户互动。"
            
            # 获取当前对话的人格设置
            if conversation:
                context = json.loads(conversation.history)
                persona_id = conversation.persona_id
                
                # 获取对话使用的人格设置
                if persona_id is None:
                    # 使用默认人格
                    default_persona = self.context.provider_manager.selected_default_persona
                    if default_persona:
                        system_prompt = default_persona.get('prompt', system_prompt)
                elif persona_id != "[%None]":
                    # 使用指定人格
                    try:
                        personas = self.context.provider_manager.personas
                        for persona in personas:
                            if persona.get('id') == persona_id:
                                system_prompt = persona.get('prompt', system_prompt)
                                break
                    except Exception as e:
                        logger.error(f"获取人格信息时出错: {str(e)}")
            

            greeting_type_name = "早安" if greeting_type == "morning" else "晚安"
            
            # 随机选择一个base prompt并添加时间信息和人设要求
            base_prompt = random.choice(prompts)
            prompt = f"{base_prompt}，请保持与你的人格设定一致的风格，确保回复符合你的人设特点。"
            
            # 获取LLM工具管理器
            func_tools_mgr = self.context.get_llm_tool_manager()
            
            # 调用LLM获取回复
            logger.info(f"正在为用户 {user_id} 生成{greeting_type_name}消息内容...")
            logger.info(f"使用的提示词: {prompt}")
            
            llm_response = await self.context.get_using_provider().text_chat(
                prompt=prompt,
                session_id=None,
                contexts=context,
                image_urls=[],
                func_tool=func_tools_mgr,
                system_prompt=system_prompt
            )
            
            # 获取回复文本
            if llm_response.role == "assistant":
                message_text = llm_response.completion_text
                
                # 使用MessageChain构造消息
                from astrbot.api.all import MessageChain
                message_chain = MessageChain().message(message_text)
                
                # 直接发送消息
                await self.context.send_message(unified_msg_origin, message_chain)
                
                # 记录日志
                logger.info(f"已向用户 {user_id} 发送{greeting_type_name}消息: {message_text}")
                
                # 将用户添加到已接收主动消息用户集合中，用于检测用户回复
                self.parent.users_received_initiative.add(user_id)
                
            else:
                logger.error(f"生成消息失败，LLM响应角色错误: {llm_response.role}")
                
        except asyncio.CancelledError:
            logger.info(f"发送给用户 {user_id} 的问候消息任务已被取消")
        except Exception as e:
            logger.error(f"发送问候消息时发生错误: {str(e)}")
