#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
任務持久化模組
負責將任務數據保存到磁盤並在應用啟動時恢復
"""

import os
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional
import time

logger = logging.getLogger("task_persistence")

# 任務數據存儲文件
TASKS_DATA_FILE = Path("tasks_data.json")
OUTPUTS_DIR = Path("outputs")


class TaskPersistence:
    """任務持久化管理器"""
    
    @staticmethod
    def save_task(task_id: str, task_data: Dict[str, Any]) -> bool:
        """
        保存單個任務數據到磁盤
        
        Args:
            task_id: 任務 ID
            task_data: 任務數據字典
            
        Returns:
            bool: 是否成功保存
        """
        try:
            # 讀取現有任務數據
            all_tasks = TaskPersistence.load_all_tasks()
            
            # 更新任務數據
            all_tasks[task_id] = task_data
            
            # 保存到文件
            with open(TASKS_DATA_FILE, 'w', encoding='utf-8') as f:
                json.dump(all_tasks, f, ensure_ascii=False, indent=2, default=str)
            
            logger.debug(f"任務 {task_id} 已保存到磁盤")
            return True
            
        except Exception as e:
            logger.error(f"保存任務 {task_id} 時出錯: {str(e)}", exc_info=True)
            return False
    
    @staticmethod
    def load_all_tasks() -> Dict[str, Any]:
        """
        從磁盤載入所有任務數據
        
        Returns:
            Dict[str, Any]: 所有任務數據
        """
        try:
            if not TASKS_DATA_FILE.exists():
                logger.info("任務數據文件不存在，返回空字典")
                return {}
            
            with open(TASKS_DATA_FILE, 'r', encoding='utf-8') as f:
                tasks = json.load(f)
            
            logger.info(f"從磁盤載入了 {len(tasks)} 個任務")
            return tasks
            
        except Exception as e:
            logger.error(f"載入任務數據時出錯: {str(e)}", exc_info=True)
            return {}
    
    @staticmethod
    def delete_task(task_id: str) -> bool:
        """
        從磁盤刪除任務數據
        
        Args:
            task_id: 任務 ID
            
        Returns:
            bool: 是否成功刪除
        """
        try:
            all_tasks = TaskPersistence.load_all_tasks()
            
            if task_id in all_tasks:
                del all_tasks[task_id]
                
                with open(TASKS_DATA_FILE, 'w', encoding='utf-8') as f:
                    json.dump(all_tasks, f, ensure_ascii=False, indent=2, default=str)
                
                logger.info(f"任務 {task_id} 已從磁盤刪除")
                return True
            else:
                logger.warning(f"任務 {task_id} 不存在於磁盤")
                return False
                
        except Exception as e:
            logger.error(f"刪除任務 {task_id} 時出錯: {str(e)}", exc_info=True)
            return False
    
    @staticmethod
    def scan_and_rebuild_tasks() -> Dict[str, Any]:
        """
        掃描 outputs 目錄，重建任務列表
        這個方法用於從現有的輸出文件恢復任務信息
        
        Returns:
            Dict[str, Any]: 重建的任務數據
        """
        rebuilt_tasks = {}
        
        try:
            if not OUTPUTS_DIR.exists():
                logger.warning(f"輸出目錄 {OUTPUTS_DIR} 不存在")
                return rebuilt_tasks
            
            # 遍歷輸出目錄中的每個任務文件夾
            for task_dir in OUTPUTS_DIR.iterdir():
                if not task_dir.is_dir():
                    continue
                
                task_id = task_dir.name
                
                # 查找 JSON 文件
                json_files = list(task_dir.glob("*.json"))
                if not json_files:
                    logger.debug(f"任務 {task_id} 沒有 JSON 文件，跳過")
                    continue
                
                # 使用第一個 JSON 文件
                json_file = json_files[0]
                
                # 讀取 JSON 文件獲取元數據
                try:
                    with open(json_file, 'r', encoding='utf-8') as f:
                        transcription_data = json.load(f)
                except Exception as e:
                    logger.error(f"讀取任務 {task_id} 的 JSON 文件失敗: {str(e)}")
                    continue
                
                # 查找所有輸出文件
                output_files = {}
                for ext in ['json', 'srt', 'vtt', 'txt']:
                    matching_files = list(task_dir.glob(f"*.{ext}"))
                    if matching_files:
                        # 優先選擇 updated 文件
                        updated_files = [f for f in matching_files if 'updated' in f.name]
                        if updated_files:
                            output_files[ext] = str(updated_files[0])
                        else:
                            output_files[ext] = str(matching_files[0])
                
                # 獲取文件修改時間作為完成時間
                creation_time = task_dir.stat().st_ctime
                modification_time = json_file.stat().st_mtime
                
                # 構建任務數據
                task_data = {
                    "id": task_id,
                    "status": "completed",
                    "progress": 100.0,
                    "message": "轉錄完成（從文件系統恢復）",
                    "result": {
                        "files": output_files,
                        "output_dir": str(task_dir)
                    },
                    "error": None,
                    "start_time": creation_time,
                    "end_time": modification_time
                }
                
                rebuilt_tasks[task_id] = task_data
                logger.info(f"從文件系統恢復任務: {task_id}")
            
            logger.info(f"從文件系統重建了 {len(rebuilt_tasks)} 個任務")
            
            # 如果重建了任務，保存到磁盤
            if rebuilt_tasks:
                try:
                    with open(TASKS_DATA_FILE, 'w', encoding='utf-8') as f:
                        json.dump(rebuilt_tasks, f, ensure_ascii=False, indent=2, default=str)
                    logger.info("重建的任務數據已保存到磁盤")
                except Exception as e:
                    logger.error(f"保存重建的任務數據時出錯: {str(e)}")
            
            return rebuilt_tasks
            
        except Exception as e:
            logger.error(f"掃描和重建任務時出錯: {str(e)}", exc_info=True)
            return rebuilt_tasks
    
    @staticmethod
    def initialize_tasks() -> Dict[str, Any]:
        """
        初始化任務數據
        優先從持久化文件載入，如果不存在則從文件系統重建
        
        Returns:
            Dict[str, Any]: 初始化的任務數據
        """
        # 嘗試從持久化文件載入
        tasks = TaskPersistence.load_all_tasks()
        
        # 如果沒有持久化數據，嘗試從文件系統重建
        if not tasks:
            logger.info("沒有找到持久化的任務數據，嘗試從文件系統重建...")
            tasks = TaskPersistence.scan_and_rebuild_tasks()
        
        return tasks