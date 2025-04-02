import asyncio
import datetime
import json
import logging
import random
import time
from typing import Dict, Any, Set, Optional

from astrbot.api.all import logger, AstrMessageEvent, MessageChain
from astrbot.api.provider import ProviderRequest

class InitiativeDialogueCore:
    """主动对话核心功能模块"""
    def __init__(self, plugin_instance):
        """初始化主动对话核心
        
        Args:
            plugin_instance: 插件实例，用于访问上下文和配置
        """
        self.plugin = plugin_instance
        self.context = plugin_instance.context
        
        # 从插件实例获取配置
        self.config = plugin_instance.config or {}
        self.time_settings = self.config.get('time_settings', {})
        self.whitelist_config = self.config.get('whitelist', {})
        
        # 存储用户的会话记录
        self.user_records = {}
        
        # 跟踪最近收到过主动消息的用户，用于检测用户回复
        self.users_received_initiative = set()
        
        # 存储用户最后一次对话的信息
        self.last_initiative_messages = {}
        
        # 设置时间参数
        self.time_limit_enabled = self.time_settings.get('time_limit_enabled', True)
        self.inactive_time_seconds = self.time_settings.get('inactive_time_seconds', 7200)
        self.max_response_delay_seconds = self.time_settings.get('max_response_delay_seconds', 3600)
        self.activity_start_hour = self.time_settings.get('activity_start_hour', 8)
        self.activity_end_hour = self.time_settings.get('activity_end_hour', 23)
        
        # 白名单设置
        self.whitelist_enabled = self.whitelist_config.get('enabled', False)
        self.whitelist_users = set(self.whitelist_config.get('user_ids', []))
        
        # 预设的prompt列表 - 直接在代码中定义，不再从配置加载
        self.prompts = [
            "请以调皮可爱的语气，用简短的一句话表达我很想念用户，希望他/她能来陪我聊天",
            "请以略带不满的语气，用简短的一句话表达用户很久没有理你，你有点生气了",
            "请以撒娇的语气，用简短的一句话问候用户，表示很想念他/她",
            "请以可爱的语气，用简短的一句话表达你很无聊，希望用户能来陪你聊天",
            "请以委屈的语气，用简短的一句话问用户是不是把你忘了",
            "请以俏皮的语气，用简短的一句话表达你在等用户来找你聊天",
            "请以温柔的语气，用简短的一句话表达你想知道用户最近过得怎么样",
            "请以可爱的语气，用简短的一句话提醒用户你还在这里等他/她",
            "请以友好的语气，用简短的一句话问用户最近是不是很忙",
            "请以亲切的语气，用简短的一句话表达你希望用户能告诉你他/她的近况"
        ]
        
        # 深夜时段的prompt列表 (0点到7点) - 直接在代码中定义，不再从配置加载
        self.night_prompts = [
            "请以轻声细语的语气，用简短的一句话表达你失眠了，想和用户聊聊天",
            "请以温柔梦幻的语气，用简短的一句话表达你非常想念用户，以至于睡不着想和他/她说说话",
            "请以好奇的语气，用简短的一句话询问用户是否还醒着，如果醒着能不能陪陪你",
            "请以略带寂寞的语气，用简短的一句话表达在这个深夜里你很想和用户聊聊天",
            "请以柔和的语气，用简短的一句话表达看到用户还在线感到很开心，想问问用户为什么这么晚还没睡",
            "请以安静的语气，用简短的一句话表达夜深人静的时候你总会想起用户",
            "请以轻松的语气，用简短的一句话表达你在想用户睡了没有，有点想和他/她聊天"
        ]
        
        # 存储消息任务的字典
        self._message_tasks = {}
        
        # 主要检查任务引用
        self.message_check_task = None
        self.tasks = {}
        
        logger.info("主动对话核心模块初始化完成")
        
    def set_data(self, user_records=None, last_initiative_messages=None, users_received_initiative=None):
        """从外部设置数据"""
        if user_records is not None:
            self.user_records = user_records
        if last_initiative_messages is not None:
            self.last_initiative_messages = last_initiative_messages
        if users_received_initiative is not None:
            self.users_received_initiative = users_received_initiative
            
    def get_data(self):
        """获取核心数据，用于保存"""
        return {
            'user_records': self.user_records,
            'last_initiative_messages': self.last_initiative_messages,
            'users_received_initiative': list(self.users_received_initiative)
        }
    
    async def handle_user_message(self, user_id: str, event: AstrMessageEvent):
        """处理用户消息，更新状态并取消待发送消息"""
        current_time = datetime.datetime.now()
        
        # 检查用户是否刚收到过主动消息
        user_responding_to_initiative = user_id in self.users_received_initiative
        if user_responding_to_initiative:
            logger.info(f"用户 {user_id} 回复了主动消息，将在LLM请求钩子中添加欣喜表达")
        
        # 取消为该用户安排的待发送消息任务
        tasks_to_cancel = []
        for task_id, task in list(self._message_tasks.items()):
            if task_id.startswith(f"send_message_{user_id}_") and not task.done():
                tasks_to_cancel.append((task_id, task))
        
        # 取消找到的任务
        for task_id, task in tasks_to_cancel:
            task.cancel()
            self._message_tasks.pop(task_id, None)
            logger.info(f"由于用户 {user_id} 发送新消息，已取消待发送的主动消息任务 {task_id}")
        
        # 获取当前的会话ID
        curr_cid = await self.context.conversation_manager.get_curr_conversation_id(event.unified_msg_origin)
        
        # 如果没有会话ID，创建一个新的
        if not curr_cid:
            curr_cid = await self.context.conversation_manager.new_conversation(event.unified_msg_origin)
        
        # 检查用户是否在白名单中
        is_whitelisted = True
        if self.whitelist_enabled:
            is_whitelisted = user_id in self.whitelist_users
        
        # 更新或创建用户记录（仅当用户在白名单中或白名单未启用时）
        if is_whitelisted:
            self.user_records[user_id] = {
                'conversation_id': curr_cid,
                'timestamp': current_time,
                'unified_msg_origin': event.unified_msg_origin
            }
            logger.info(f"用户 {user_id} 已加入主动对话监控，当前监控总数: {len(self.user_records)}，会话ID: {curr_cid}")
            return True
        else:
            logger.info(f"用户 {user_id} 未在白名单中，不加入监控")
            return False
    
    def modify_llm_request_for_initiative_response(self, user_id: str, req: ProviderRequest) -> bool:
        """为回复主动消息修改LLM请求"""
        if user_id in self.users_received_initiative:
            logger.info(f"[钩子触发] 检测到用户 {user_id} 正在回复主动消息，添加欣喜表达提示")
            
            # 修改用户提示词，添加对用户回复的欣喜反应
            original_prompt = req.prompt or ""
            excitement_addition = "\n请注意：用户刚刚回复了你的主动消息，这表明用户关注到了你。请在回复的开头一定要明确表达出你对用户回复的欣喜和感激之情，语气要热情、自然。之后再正常回答用户的问题。即使用户只是简单回复'嗯'、'哦'等词语，也要表现出欣喜情绪。"
            req.prompt = original_prompt + excitement_addition
            
            # 从集合中移除用户，避免重复处理
            self.users_received_initiative.remove(user_id)
            logger.info(f"[钩子日志] 已从回复检测集合中移除用户 {user_id}")
            
            # 检查是否有该用户过去私聊的记录
            found_private_chat = False
            
            # 查询历史监控记录
            for u_id, record in list(self.user_records.items()):
                if u_id == user_id:
                    # 用户当前在监控列表中，需要重置其连续发送计数
                    logger.info(f"[钩子日志] 用户 {user_id} 已在监控列表中，重置连续发送计数为0")
                    record['consecutive_count'] = 0  # 重置连续计数为0
                    record['timestamp'] = datetime.datetime.now()  # 更新时间戳
                    found_private_chat = True
                    break
            
            # 如果没有当前记录，尝试从存储的最后消息记录中恢复
            if not found_private_chat and user_id in self.last_initiative_messages:
                last_msg_info = self.last_initiative_messages[user_id]
                logger.info(f"[钩子日志] 从历史主动消息记录中找到用户 {user_id} 的私聊信息，重新加入监控")
                current_time = datetime.datetime.now()
                self.user_records[user_id] = {
                    'conversation_id': last_msg_info['conversation_id'],
                    'timestamp': current_time,
                    'unified_msg_origin': last_msg_info['unified_msg_origin'],
                    'consecutive_count': 0  # 重置连续计数，因为用户已回复
                }
                found_private_chat = True
            
            if not found_private_chat:
                logger.warning(f"[钩子日志] 用户 {user_id} 没有找到历史私聊记录，无法重新加入监控")
                
            return True
        return False
    
    async def start_checking_inactive_conversations(self):
        """启动检查不活跃对话的任务"""
        self.message_check_task = asyncio.create_task(self._check_inactive_conversations())
        self.tasks["check_inactive"] = self.message_check_task
        logger.info("已启动检查不活跃对话的任务")
        
    async def stop_checking_inactive_conversations(self):
        """停止检查不活跃对话的任务"""
        if self.message_check_task:
            self.message_check_task.cancel()
            logger.info("已取消检查不活跃对话的任务")
        
        # 取消所有待发送的消息任务
        task_count = len(self._message_tasks)
        for task_id, task in list(self._message_tasks.items()):
            if not task.done():
                task.cancel()
        logger.info(f"已取消 {task_count} 个待发送的消息任务")
    
    async def _check_inactive_conversations(self):
        """定期检查不活跃的会话，并发送主动消息"""
        try:
            while True:
                current_time = datetime.datetime.now()
                
                # 检查当前时间是否在允许的活动时间段内
                current_hour = current_time.hour
                is_active_time = True  # 默认为活动时间
                
                if self.time_limit_enabled:
                    # 修改判断逻辑：深夜时段(0-7点)也允许发送消息，但会使用特殊的prompt
                    is_active_time = (self.activity_start_hour <= current_hour < self.activity_end_hour) or (0 <= current_hour < 7)
                
                if is_active_time and self.user_records:  # 只有当有用户记录时才继续处理
                    users_to_message = []
                    
                    # 检查每个用户记录
                    for user_id, record in list(self.user_records.items()):
                        # 如果启用白名单，检查用户是否在白名单中
                        if self.whitelist_enabled and user_id not in self.whitelist_users:
                            # 从记录中移除非白名单用户
                            self.user_records.pop(user_id, None)
                            logger.info(f"用户 {user_id} 不在白名单中，已从监控记录中移除")
                            continue
                            
                        # 计算自上次消息以来的时间（秒）
                        seconds_elapsed = (current_time - record['timestamp']).total_seconds()
                        
                        # 检查是否在发送窗口期内
                        if seconds_elapsed >= (self.inactive_time_seconds + self.max_response_delay_seconds):
                            # 重置这些用户的记录
                            record['timestamp'] = current_time
                            continue
                        
                        # 只处理那些刚好超过不活跃阈值但未超过阈值+窗口时间的记录
                        if self.inactive_time_seconds <= seconds_elapsed < (self.inactive_time_seconds + self.max_response_delay_seconds):
                            users_to_message.append((user_id, record))
                    
                    # 为每个需要发送消息的用户安排一个随机时间发送
                    if users_to_message:
                        logger.info(f"发现 {len(users_to_message)} 个需要发送主动消息的用户")
                        
                    for user_id, record in users_to_message:
                        # 计算还剩多少时间到窗口结束
                        seconds_elapsed = (current_time - record['timestamp']).total_seconds()
                        max_delay = min(self.inactive_time_seconds + self.max_response_delay_seconds - seconds_elapsed, 
                                       self.max_response_delay_seconds)
                        
                        # 在剩余时间内随机选择一个时间点
                        delay = random.randint(1, int(max_delay))
                        
                        # 获取连续发送计数
                        consecutive_count = record.get('consecutive_count', 0) + 1
                        
                        # 创建并存储任务
                        task_id = f"send_message_{user_id}_{int(time.time())}"
                        task = asyncio.create_task(self._send_initiative_message(
                            user_id=user_id,
                            conversation_id=record['conversation_id'],
                            unified_msg_origin=record['unified_msg_origin'],
                            delay_seconds=delay,
                            consecutive_count=consecutive_count
                        ))
                        
                        self._message_tasks[task_id] = task
                        
                        # 设置清理回调
                        def remove_task(t, tid=task_id):
                            if tid in self._message_tasks:
                                self._message_tasks.pop(tid, None)
                            
                        task.add_done_callback(remove_task)
                        
                        # 从记录中移除该用户
                        self.user_records.pop(user_id, None)
                        
                        scheduled_time = current_time + datetime.timedelta(seconds=delay)
                        logger.info(f"为用户 {user_id} 安排在 {delay} 秒后({scheduled_time.strftime('%H:%M:%S')})发送主动消息，连续发送次数: {consecutive_count}")
                
                # 每10秒检查一次，提高时间精度
                await asyncio.sleep(10)
                
        except asyncio.CancelledError:
            logger.info("检查不活跃会话的任务已取消")
        except Exception as e:
            logger.error(f"检查不活跃会话时发生错误: {str(e)}")
            # 尝试重新启动检查任务
            logger.info("尝试重新启动检查任务")
            await asyncio.sleep(5)
            await self.start_checking_inactive_conversations()
    
    async def _send_initiative_message(self, user_id, conversation_id, unified_msg_origin, delay_seconds, consecutive_count=1):
        """在指定延迟后发送主动消息"""
        try:
            # 等待指定时间
            await asyncio.sleep(delay_seconds)
            
            # 再次检查用户是否在白名单中
            if self.whitelist_enabled and user_id not in self.whitelist_users:
                logger.info(f"用户 {user_id} 不再在白名单中，取消发送主动消息")
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
            
            # 设置最大连续发送次数
            max_consecutive_messages = self.time_settings.get('max_consecutive_messages', 3)
            
            # 根据当前时间选择不同的prompts列表
            current_hour = datetime.datetime.now().hour
            if 0 <= current_hour < 7:  # 凌晨0点到7点
                logger.info(f"当前是深夜时段({current_hour}点)，使用深夜问候语")
                prompt_list = self.night_prompts
            else:  # 其他时间
                prompt_list = self.prompts
                
            # 随机选择一个prompt
            base_prompt = random.choice(prompt_list)
            
            # 根据连续发送次数调整prompt
            adjusted_prompt = base_prompt
            if consecutive_count == max_consecutive_messages:  # 最后一次发送
                adjusted_prompt = f"假设这是你最后一次主动联系用户，之前已经联系了{consecutive_count-1}次但用户都没有回复。请用简短的一句话，表达你对用户一直不回复感到失望和伤心，同时表示你理解他/她可能很忙，以后不会再主动打扰，但会一直等待用户回来找你聊天的。保持与你的人格设定一致的风格。"
            elif consecutive_count > 1:
                # 如果这是连续的第N次发送，调整提示词
                adjusted_prompt = f"假设这是你第{consecutive_count}次主动联系用户，但用户仍然没有回复你。{base_prompt}，请表达出你的耐心等待和真诚期待，但不要表现得过于急切或打扰用户。"
            else:
                adjusted_prompt = f"{base_prompt}，请保持与你的人格设定一致的风格"
            
            # 获取LLM工具管理器
            func_tools_mgr = self.context.get_llm_tool_manager()
            
            # 调用LLM获取回复
            logger.info(f"正在为用户 {user_id} 生成主动消息内容...")
            llm_response = await self.context.get_using_provider().text_chat(
                prompt=adjusted_prompt,
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
                message_chain = MessageChain().message(message_text)
                
                # 直接发送消息
                await self.context.send_message(unified_msg_origin, message_chain)
                
                # 记录日志
                logger.info(f"已向用户 {user_id} 发送第 {consecutive_count} 条连续主动消息: {message_text}")
                
                # 将用户添加到已接收主动消息用户集合中，用于检测用户回复
                self.users_received_initiative.add(user_id)
                logger.info(f"用户 {user_id} 已添加到主动消息回复检测中，当前集合大小: {len(self.users_received_initiative)}")
                
                # 保存最后一次主动消息的信息
                self.last_initiative_messages[user_id] = {
                    'conversation_id': conversation_id,
                    'unified_msg_origin': unified_msg_origin,
                    'timestamp': datetime.datetime.now()
                }
                
                # 如果未超过最大连续发送次数，将用户重新加入记录以继续监控
                if consecutive_count < max_consecutive_messages:
                    current_time = datetime.datetime.now()
                    # 将用户重新添加到记录中，以重新开始计时
                    self.user_records[user_id] = {
                        'conversation_id': conversation_id,
                        'timestamp': current_time,
                        'unified_msg_origin': unified_msg_origin,
                        'consecutive_count': consecutive_count  # 记录已经连续发送的次数
                    }
                    logger.info(f"用户 {user_id} 未回复，已重新加入监控记录，当前连续发送次数: {consecutive_count}")
                else:
                    logger.info(f"用户 {user_id} 已达到最大连续发送次数({max_consecutive_messages})，停止连续发送")
            else:
                logger.error(f"生成消息失败，LLM响应角色错误: {llm_response.role}")
                
        except asyncio.CancelledError:
            logger.info(f"发送给用户 {user_id} 的主动消息任务已被取消")
        except Exception as e:
            logger.error(f"发送主动消息时发生错误: {str(e)}")
