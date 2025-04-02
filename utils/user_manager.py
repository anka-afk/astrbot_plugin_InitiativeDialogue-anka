# 用户管理器 - 处理用户选择和筛选逻辑

import random
import logging
from typing import List, Dict, Any, Set, Tuple

logger = logging.getLogger("user_manager")


class UserManager:
    """用户管理器，负责选择和筛选符合条件的用户"""

    def __init__(self, parent):
        """初始化用户管理器

        Args:
            parent: 父插件实例，用于访问核心组件
        """
        self.parent = parent


    @property
    def dialogue_core(self):
        """延迟获取dialogue_core属性"""
        return self.parent.dialogue_core

    def get_eligible_users(
        self, excluded_users: Set[str]
    ) -> List[Tuple[str, Dict[str, Any]]]:
        """获取符合条件的用户（未在排除集合中且在白名单内）

        Args:
            excluded_users: 要排除的用户ID集合

        Returns:
            List[Tuple[str, Dict]]: 符合条件的用户ID和用户记录元组列表
        """
        eligible_users = []

        # 检查现有用户记录
        for user_id, record in list(self.dialogue_core.user_records.items()):
            # 检查是否已经在排除集合中
            if user_id in excluded_users:
                continue

            # 检查是否在白名单中
            if (
                self.dialogue_core.whitelist_enabled
                and user_id not in self.dialogue_core.whitelist_users
            ):
                continue

            # 符合条件的用户
            eligible_users.append((user_id, record))

        # 检查历史用户记录
        if hasattr(self.dialogue_core, "last_initiative_messages"):
            for user_id, record in list(
                self.dialogue_core.last_initiative_messages.items()
            ):
                # 跳过已在结果中的用户
                if any(uid == user_id for uid, _ in eligible_users):
                    continue

                # 检查是否已经在排除集合中
                if user_id in excluded_users:
                    continue

                # 检查是否在白名单中
                if (
                    self.dialogue_core.whitelist_enabled
                    and user_id not in self.dialogue_core.whitelist_users
                ):
                    continue

                # 符合条件的用户
                eligible_users.append(
                    (
                        user_id,
                        {
                            "conversation_id": record["conversation_id"],
                            "unified_msg_origin": record["unified_msg_origin"],
                        },
                    )
                )

        return eligible_users

    def select_random_users(
        self,
        eligible_users: List[Tuple[str, Dict[str, Any]]],
        selection_ratio: float = 0.3,
        min_count: int = 1,
    ) -> List[Tuple[str, Dict[str, Any]]]:
        """从符合条件的用户中随机选择一部分

        Args:
            eligible_users: 符合条件的用户列表
            selection_ratio: 选择比例（0-1之间）
            min_count: 最小选择数量

        Returns:
            List[Tuple[str, Dict]]: 选中的用户列表
        """
        if not eligible_users:
            return []

        user_count = len(eligible_users)
        selection_count = max(min_count, int(user_count * selection_ratio))
        selected_users = random.sample(eligible_users, min(selection_count, user_count))

        return selected_users

    def is_user_in_whitelist(self, user_id: str) -> bool:
        """检查用户是否在白名单中

        Args:
            user_id: 用户ID

        Returns:
            bool: 是否在白名单中
        """
        if not self.dialogue_core.whitelist_enabled:
            return True

        return user_id in self.dialogue_core.whitelist_users