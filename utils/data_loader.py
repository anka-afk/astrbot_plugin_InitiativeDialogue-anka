# 单例模式数据读取器

import asyncio
import datetime
import json
from astrbot.api import logger
from typing import Dict, Any


class DataLoader:
    """数据加载器, 单例模式"""

    _instance = None

    @classmethod
    def get_instance(cls, plugin_instance=None):
        if cls._instance is None and plugin_instance is not None:
            cls._instance = cls(plugin_instance)
        return cls._instance

    def __init__(self, plugin_instance):
        if DataLoader._instance is not None:
            raise RuntimeError("Please use get_instance() to access the instance.")
        self.plugin = plugin_instance
        self.data_dir = plugin_instance.data_dir
        self.data_file = plugin_instance.data_file
        self.dialogue_core = plugin_instance.dialogue_core

        self.save_data_task = None

        DataLoader._instance = self

    def load_data_from_storage(self) -> None:
        try:
            if self.data_file.exists():
                with open(self.data_file, "r", encoding="utf-8") as f:
                    stored_data = json.load(f)

                    if "user_records" in stored_data:
                        for user_id, record in stored_data["user_records"].items():
                            if "timestamp" in record and isinstance(
                                record["timestamp"], str
                            ):
                                try:
                                    record["timestamp"] = (
                                        datetime.datetime.fromisoformat(
                                            record["timestamp"]
                                        )
                                    )
                                except ValueError:
                                    record["timestamp"] = datetime.datetime.now()
                    if "last_initiative_messages" in stored_data:
                        for user_id, record in stored_data[
                            "last_initiative_messages"
                        ].items():
                            if "timestamp" in record and isinstance(
                                record["timestamp"], str
                            ):
                                try:
                                    record["timestamp"] = (
                                        datetime.datetime.fromisoformat(
                                            record["timestamp"]
                                        )
                                    )
                                except ValueError:
                                    record["timestamp"] = datetime.datetime.now()

                    self.dialogue_core.set_data(
                        user_records=stored_data.get("user_records", {}),
                        last_initiative_messages=stored_data.get(
                            "last_initiative_messages", {}
                        ),
                        users_received_initiative=set(
                            stored_data.get("users_received_initiative", [])
                        ),
                    )
            logger.info(f"成功从 {self.data_file} 加载用户数据")
        except Exception as e:
            logger.error(f"从存储加载数据时发生错误: {str(e)}")

    def save_data_to_storage(self) -> None:
        """将数据保存到本地存储"""
        try:
            core_data = self.dialogue_core.get_data()

            data_to_save = {
                "user_records": self._prepare_records_for_save(
                    core_data.get("user_records", {})
                ),
                "last_initiative_messages": self._prepare_records_for_save(
                    core_data.get("last_initiative_messages", {})
                ),
                "users_received_initiative": list(
                    core_data.get("users_received_initiative", [])
                ),
            }

            with open(self.data_file, "w", encoding="utf-8") as f:
                json.dump(data_to_save, f, ensure_ascii=False, indent=2)

            logger.info(f"数据已保存到 {self.data_file}")
        except Exception as e:
            logger.error(f"保存数据到存储时发生错误: {str(e)}")

    def _prepare_records_for_save(self, records: Dict[str, Any]) -> Dict[str, Any]:
        """准备记录以便保存，将datetime对象转换为ISO格式字符串"""
        prepared_records = {}

        for user_id, record in records.items():
            record_copy = dict(record)

            if "timestamp" in record_copy and isinstance(
                record_copy["timestamp"], datetime.datetime
            ):
                record_copy["timestamp"] = record_copy["timestamp"].isoformat()

            prepared_records[user_id] = record_copy

        return prepared_records

    async def start_periodic_save(self) -> None:
        """启动定期保存数据的任务"""
        if self.save_data_task is not None:
            logger.warning("定期保存数据任务已在运行中")
            return

        logger.info("启动定期保存数据任务")
        self.save_data_task = asyncio.create_task(self._periodic_save_data())

    async def stop_periodic_save(self) -> None:
        """停止定期保存数据的任务"""
        if self.save_data_task is not None and not self.save_data_task.done():
            self.save_data_task.cancel()
            try:
                await self.save_data_task
            except asyncio.CancelledError:
                pass

            self.save_data_task = None
            logger.info("定期保存数据任务已取消")

    async def _periodic_save_data(self) -> None:
        """定期保存数据的异步任务"""
        try:
            while True:
                await asyncio.sleep(300)
                self.save_data_to_storage()
        except asyncio.CancelledError:
            self.save_data_to_storage()
            logger.info("定期保存数据任务已取消")
            raise
        except Exception as e:
            logger.error(f"定期保存数据任务发生错误: {str(e)}")
