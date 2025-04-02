# Description: 随机日常模块，在指定时间段发送不同类型的日常消息

import asyncio
import datetime
import json
import logging
import random
from typing import Dict, Any, Set, Optional

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
        self.context = parent.context
        
        # 从父插件配置中加载随机日常配置
        self.config = parent.config.get('random_daily_activities', {})
        
        # 功能总开关
        self.enabled = self.config.get('enabled', True)
        
        # 午餐时间配置
        lunch_config = self.config.get('lunch_time', {})
        self.lunch_enabled = lunch_config.get('enabled', True)
        self.lunch_start_hour = lunch_config.get('start_hour', 11)
        self.lunch_end_hour = lunch_config.get('end_hour', 13)
        
        # 晚餐时间配置
        dinner_config = self.config.get('dinner_time', {})
        self.dinner_enabled = dinner_config.get('enabled', True)
        self.dinner_start_hour = dinner_config.get('start_hour', 17)
        self.dinner_end_hour = dinner_config.get('end_hour', 19)
        
        # 日常分享配置
        sharing_config = self.config.get('daily_sharing', {})
        self.sharing_enabled = sharing_config.get('enabled', True)
        self.min_interval_minutes = sharing_config.get('min_interval_minutes', 180)
        self.max_interval_minutes = sharing_config.get('max_interval_minutes', 360)
        
        # 午餐提示词列表
        self.lunch_prompts = [
            "请以自然的语气，简短地询问用户吃午饭了吗，可以稍微表达自己的饥饿感",
            "请以亲切的语气，简短地询问用户中午想吃什么，并分享一下你的午餐选择",
            "请以活泼的语气，简短地邀请用户一起吃午饭，可以提议一些美食选择",
            "请以随意的语气，简短地向用户抱怨一下你还没吃午饭，肚子有点饿了",
            "请以友好的语气，简短地询问用户是否需要你推荐一些午餐选择"
        ]
        
        # 晚餐提示词列表
        self.dinner_prompts = [
            "请以温和的语气，简短地询问用户晚餐打算吃什么，可以提一下你自己的想法",
            "请以轻松的语气，简短地邀请用户一起享用晚餐，可以询问用户喜欢什么口味",
            "请以惬意的语气，简短地和用户聊聊晚餐，分享你喜欢的一道晚餐菜品",
            "请以关心的语气，简短地提醒用户该吃晚饭了，可以询问用户是否已经吃过",
            "请以好奇的语气，简短地询问用户晚餐有什么安排，可以表达一点期待感"
        ]
        
        # 日常分享提示词列表（根据不同时间段）
        self.morning_sharing_prompts = [
            "请简短描述你早上刚起床时的一个日常行为或想法，内容要符合当前时间(上午)，语气要自然随意",
            "请简短分享你早上看到的一个有趣事物或现象，内容要符合当前时间(上午)，语气要轻松活泼",
            "请简短描述你早上的一个小计划或安排，内容要符合当前时间(上午)，语气要积极向上"
        ]
        
        self.afternoon_sharing_prompts = [
            "请简短描述你下午做的一个休闲活动，内容要符合当前时间(下午)，语气要轻松愉快",
            "请简短分享你下午看到或遇到的一个小趣事，内容要符合当前时间(下午)，语气要生动有趣",
            "请简短描述你下午的一个小感悟或想法，内容要符合当前时间(下午)，语气要自然平和"
        ]
        
        self.evening_sharing_prompts = [
            "请简短描述你晚上的一个放松方式，内容要符合当前时间(晚上)，语气要舒适惬意",
            "请简短分享你晚上看到的一个温馨或美好的场景，内容要符合当前时间(晚上)，语气要柔和",
            "请简短描述你晚上的一个小习惯或仪式感行为，内容要符合当前时间(晚上)，语气要亲切"
        ]
        
        self.night_sharing_prompts = [
            "请简短描述你深夜的一个安静时刻或思考，内容要符合当前时间(深夜)，语气要轻柔",
            "请简短分享你深夜喜欢做的一件小事，内容要符合当前时间(深夜)，语气要intimate",
            "请简短描述你深夜的一个小心愿或期待，内容要符合当前时间(深夜)，语气要温暖"
        ]
        
        # 跟踪用户今日已收到的消息
        self.today_lunch_users = set()
        self.today_dinner_users = set()
        self.last_sharing_time = {}  # 用户ID -> 上次分享时间
        
        # 记录最近一次检查的日期，用于重置状态
        self.last_check_date = datetime.datetime.now().date()
        
        # 主要任务引用
        self.daily_task = None
        
        logger.info(f"随机日常模块初始化完成，状态：{'启用' if self.enabled else '禁用'}")
    
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
                if (self.lunch_enabled and 
                    self.lunch_start_hour <= current_hour < self.lunch_end_hour):
                    await self._check_lunch_time()
                
                # 2. 检查是否在晚餐时间段
                if (self.dinner_enabled and 
                    self.dinner_start_hour <= current_hour < self.dinner_end_hour):
                    await self._check_dinner_time()
                
                # 3. 检查是否需要发送日常分享
                if self.sharing_enabled:
                    await self._check_daily_sharing()
                
                # 每10s检查一次
                await asyncio.sleep(10)
                
        except asyncio.CancelledError:
            logger.info("随机日常检查循环已取消")
        except Exception as e:
            logger.error(f"随机日常检查循环发生错误: {str(e)}")
    
    async def _check_lunch_time(self):
        """检查是否需要发送午餐相关消息"""
        try:
            # 获取所有符合条件的用户
            eligible_users = self._get_eligible_users(self.today_lunch_users)
            
            if not eligible_users:
                return
                
            # 随机选择一些用户发送消息（最多选择30%的用户）
            user_count = len(eligible_users)
            selection_count = max(1, int(user_count * 0.3))
            selected_users = random.sample(list(eligible_users), min(selection_count, user_count))
            
            for user_id, record in selected_users:
                # 为每个用户安排30分钟内随机时间发送消息
                delay_minutes = random.randint(1, 30)
                
                # 创建异步任务发送午餐消息
                task_id = f"lunch_{user_id}_{int(datetime.datetime.now().timestamp())}"
                task = asyncio.create_task(self._send_meal_message(
                    user_id=user_id,
                    conversation_id=record['conversation_id'],
                    unified_msg_origin=record['unified_msg_origin'],
                    message_type="lunch",
                    delay_minutes=delay_minutes,
                    prompts=self.lunch_prompts
                ))
                
                # 存储任务
                if not hasattr(self.parent, '_message_tasks'):
                    self.parent._message_tasks = {}
                    
                self.parent._message_tasks[task_id] = task
                
                # 设置清理回调
                def remove_task(t, tid=task_id):
                    if tid in self.parent._message_tasks:
                        self.parent._message_tasks.pop(tid, None)
                
                task.add_done_callback(remove_task)
                
                # 将用户添加到今日已发送集合
                self.today_lunch_users.add(user_id)
                
                scheduled_time = datetime.datetime.now() + datetime.timedelta(minutes=delay_minutes)
                logger.info(f"为用户 {user_id} 安排在 {delay_minutes} 分钟后({scheduled_time.strftime('%H:%M')})发送午餐询问消息")
                
        except Exception as e:
            logger.error(f"检查午餐时间任务时发生错误: {str(e)}")
    
    async def _check_dinner_time(self):
        """检查是否需要发送晚餐相关消息"""
        try:
            # 获取所有符合条件的用户
            eligible_users = self._get_eligible_users(self.today_dinner_users)
            
            if not eligible_users:
                return
                
            # 随机选择一些用户发送消息（最多选择30%的用户）
            user_count = len(eligible_users)
            selection_count = max(1, int(user_count * 0.3))
            selected_users = random.sample(list(eligible_users), min(selection_count, user_count))
            
            for user_id, record in selected_users:
                # 为每个用户安排30分钟内随机时间发送消息
                delay_minutes = random.randint(1, 30)
                
                # 创建异步任务发送晚餐消息
                task_id = f"dinner_{user_id}_{int(datetime.datetime.now().timestamp())}"
                task = asyncio.create_task(self._send_meal_message(
                    user_id=user_id,
                    conversation_id=record['conversation_id'],
                    unified_msg_origin=record['unified_msg_origin'],
                    message_type="dinner",
                    delay_minutes=delay_minutes,
                    prompts=self.dinner_prompts
                ))
                
                # 存储任务
                if not hasattr(self.parent, '_message_tasks'):
                    self.parent._message_tasks = {}
                    
                self.parent._message_tasks[task_id] = task
                
                # 设置清理回调
                def remove_task(t, tid=task_id):
                    if tid in self.parent._message_tasks:
                        self.parent._message_tasks.pop(tid, None)
                
                task.add_done_callback(remove_task)
                
                # 将用户添加到今日已发送集合
                self.today_dinner_users.add(user_id)
                
                scheduled_time = datetime.datetime.now() + datetime.timedelta(minutes=delay_minutes)
                logger.info(f"为用户 {user_id} 安排在 {delay_minutes} 分钟后({scheduled_time.strftime('%H:%M')})发送晚餐询问消息")
                
        except Exception as e:
            logger.error(f"检查晚餐时间任务时发生错误: {str(e)}")
    
    async def _check_daily_sharing(self):
        """检查是否需要发送日常分享消息"""
        try:
            now = datetime.datetime.now()
            
            # 获取所有符合条件的用户
            eligible_users = []
            
            # 检查现有用户记录
            for user_id, record in list(self.parent.dialogue_core.user_records.items()):
                # 检查是否在白名单中
                if self.parent.dialogue_core.whitelist_enabled and user_id not in self.parent.dialogue_core.whitelist_users:
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
                        ratio = (minutes_since_last - self.min_interval_minutes) / (self.max_interval_minutes - self.min_interval_minutes)
                        probability = ratio * 0.8  # 最高80%概率
                else:
                    # 首次分享，50%概率
                    probability = 0.5
                
                # 根据概率决定是否发送
                if random.random() <= probability:
                    # 决定发送，为用户安排10分钟内随机时间发送消息
                    delay_minutes = random.randint(1, 10)
                    
                    # 选择当前时间段对应的提示词
                    current_hour = now.hour
                    if 5 <= current_hour < 12:  # 早上
                        prompts = self.morning_sharing_prompts
                    elif 12 <= current_hour < 18:  # 下午
                        prompts = self.afternoon_sharing_prompts
                    elif 18 <= current_hour < 23:  # 晚上
                        prompts = self.evening_sharing_prompts
                    else:  # 深夜
                        prompts = self.night_sharing_prompts
                    
                    # 创建异步任务发送日常分享消息
                    task_id = f"sharing_{user_id}_{int(now.timestamp())}"
                    task = asyncio.create_task(self._send_sharing_message(
                        user_id=user_id,
                        conversation_id=record['conversation_id'],
                        unified_msg_origin=record['unified_msg_origin'],
                        delay_minutes=delay_minutes,
                        prompts=prompts
                    ))
                    
                    # 存储任务
                    if not hasattr(self.parent, '_message_tasks'):
                        self.parent._message_tasks = {}
                        
                    self.parent._message_tasks[task_id] = task
                    
                    # 设置清理回调
                    def remove_task(t, tid=task_id):
                        if tid in self.parent._message_tasks:
                            self.parent._message_tasks.pop(tid, None)
                    
                    task.add_done_callback(remove_task)
                    
                    # 更新最后分享时间
                    self.last_sharing_time[user_id] = now
                    
                    scheduled_time = now + datetime.timedelta(minutes=delay_minutes)
                    logger.info(f"为用户 {user_id} 安排在 {delay_minutes} 分钟后({scheduled_time.strftime('%H:%M')})发送日常分享消息")
                
        except Exception as e:
            logger.error(f"检查日常分享任务时发生错误: {str(e)}")
    
    def _get_eligible_users(self, today_users_set):
        """获取符合条件的用户列表（未在今日发送集合中且在白名单内）"""
        eligible_users = []
        
        # 检查现有用户记录
        for user_id, record in list(self.parent.dialogue_core.user_records.items()):
            # 检查是否已经在今日发送集合中
            if user_id in today_users_set:
                continue
                
            # 检查是否在白名单中
            if self.parent.dialogue_core.whitelist_enabled and user_id not in self.parent.dialogue_core.whitelist_users:
                continue
                
            # 符合条件的用户
            eligible_users.append((user_id, record))
            
        # 检查历史用户记录
        if hasattr(self.parent.dialogue_core, 'last_initiative_messages'):
            for user_id, record in list(self.parent.dialogue_core.last_initiative_messages.items()):
                # 跳过已在结果中的用户
                if any(uid == user_id for uid, _ in eligible_users):
                    continue
                    
                # 检查是否已经在今日发送集合中
                if user_id in today_users_set:
                    continue
                    
                # 检查是否在白名单中
                if self.parent.dialogue_core.whitelist_enabled and user_id not in self.parent.dialogue_core.whitelist_users:
                    continue
                    
                # 符合条件的用户
                eligible_users.append((user_id, {
                    'conversation_id': record['conversation_id'],
                    'unified_msg_origin': record['unified_msg_origin']
                }))
        
        return eligible_users
    
    async def _send_meal_message(self, user_id, conversation_id, unified_msg_origin, 
                              message_type, delay_minutes, prompts):
        """发送用餐相关消息
        
        Args:
            user_id: 用户ID
            conversation_id: 会话ID
            unified_msg_origin: 统一消息来源
            message_type: 消息类型，"lunch" 或 "dinner"
            delay_minutes: 延迟发送的分钟数
            prompts: 可用的提示词列表
        """
        try:
            # 等待指定的延迟时间
            await asyncio.sleep(delay_minutes * 60)
            
            # 再次检查用户是否在白名单中（针对延迟期间可能发生的白名单变化）
            if self.parent.dialogue_core.whitelist_enabled and user_id not in self.parent.dialogue_core.whitelist_users:
                logger.info(f"用户 {user_id} 不再在白名单中，取消发送用餐消息")
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
            
            # 随机选择一个提示词
            prompt = random.choice(prompts)
            adjusted_prompt = f"{prompt}，请保持与你的人格设定一致的风格，确保回复符合你的人设特点。"
            
            # 获取LLM工具管理器
            func_tools_mgr = self.context.get_llm_tool_manager()
            
            # 调用LLM获取回复
            meal_type = "午餐" if message_type == "lunch" else "晚餐"
            logger.info(f"正在为用户 {user_id} 生成{meal_type}询问消息内容...")
            logger.info(f"使用的提示词: {adjusted_prompt}")
            
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
                from astrbot.api.all import MessageChain
                message_chain = MessageChain().message(message_text)
                
                # 直接发送消息
                await self.context.send_message(unified_msg_origin, message_chain)
                
                # 记录日志
                logger.info(f"已向用户 {user_id} 发送{meal_type}询问消息: {message_text}")
                
                # 将用户添加到已接收主动消息用户集合中，用于检测用户回复
                self.parent.dialogue_core.users_received_initiative.add(user_id)
                
            else:
                logger.error(f"生成消息失败，LLM响应角色错误: {llm_response.role}")
                
        except asyncio.CancelledError:
            logger.info(f"发送给用户 {user_id} 的用餐消息任务已被取消")
        except Exception as e:
            logger.error(f"发送用餐消息时发生错误: {str(e)}")
    
    async def _send_sharing_message(self, user_id, conversation_id, unified_msg_origin, 
                                 delay_minutes, prompts):
        """发送日常分享消息
        
        Args:
            user_id: 用户ID
            conversation_id: 会话ID
            unified_msg_origin: 统一消息来源
            delay_minutes: 延迟发送的分钟数
            prompts: 可用的提示词列表
        """
        try:
            # 等待指定的延迟时间
            await asyncio.sleep(delay_minutes * 60)
            
            # 再次检查用户是否在白名单中（针对延迟期间可能发生的白名单变化）
            if self.parent.dialogue_core.whitelist_enabled and user_id not in self.parent.dialogue_core.whitelist_users:
                logger.info(f"用户 {user_id} 不再在白名单中，取消发送日常分享消息")
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
            
            # 随机选择一个提示词
            prompt = random.choice(prompts)
            
            # 获取当前时间段名称
            current_hour = datetime.datetime.now().hour
            if 5 <= current_hour < 12:
                time_period = "早上"
            elif 12 <= current_hour < 18:
                time_period = "下午"
            elif 18 <= current_hour < 23:
                time_period = "晚上"
            else:
                time_period = "深夜"
                
            adjusted_prompt = f"{prompt}，现在是{time_period}，请保持与你的人格设定一致的风格，确保回复符合你的人设特点。"
            
            # 获取LLM工具管理器
            func_tools_mgr = self.context.get_llm_tool_manager()
            
            # 调用LLM获取回复
            logger.info(f"正在为用户 {user_id} 生成{time_period}日常分享消息内容...")
            logger.info(f"使用的提示词: {adjusted_prompt}")
            
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
                from astrbot.api.all import MessageChain
                message_chain = MessageChain().message(message_text)
                
                # 直接发送消息
                await self.context.send_message(unified_msg_origin, message_chain)
                
                # 记录日志
                logger.info(f"已向用户 {user_id} 发送{time_period}日常分享消息: {message_text}")
                
                # 将用户添加到已接收主动消息用户集合中，用于检测用户回复
                self.parent.dialogue_core.users_received_initiative.add(user_id)
                
            else:
                logger.error(f"生成消息失败，LLM响应角色错误: {llm_response.role}")
                
        except asyncio.CancelledError:
            logger.info(f"发送给用户 {user_id} 的日常分享消息任务已被取消")
        except Exception as e:
            logger.error(f"发送日常分享消息时发生错误: {str(e)}")
