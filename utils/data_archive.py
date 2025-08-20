import json
import gzip
import shutil
import time
from datetime import date, timedelta
from pathlib import Path
from typing import List, Dict, Any, Tuple
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DataArchiver:
    """数据归档管理器"""
    
    def __init__(self, data_dir: str = "data", archive_dir: str = "data/archive"):
        self.data_dir = Path(data_dir)
        self.archive_dir = Path(archive_dir)
        self.experiments_file = self.data_dir / "experiments.json"
        self.archive_file = self.archive_dir / "archived_experiments.json.gz"
        
        # 确保目录存在
        self.archive_dir.mkdir(parents=True, exist_ok=True)
    
    def should_archive_experiment(self, experiment: Dict[str, Any], 
                                 archive_threshold_days: int = 180) -> bool:
        """
        判断实验是否应该归档
        
        Args:
            experiment: 实验数据
            archive_threshold_days: 归档阈值天数（默认180天，约半年）
        
        Returns:
            是否应该归档
        """
        try:
            if 'end_date' not in experiment:
                return False
            
            # 如果end_date是字符串，转换为date对象
            if isinstance(experiment['end_date'], str):
                end_date = date.fromisoformat(experiment['end_date'])
            else:
                end_date = experiment['end_date']
            
            # 计算实验结束后的天数
            days_since_end = (date.today() - end_date).days
            
            # 如果实验结束超过阈值天数，则归档
            return days_since_end > archive_threshold_days
            
        except Exception as e:
            logger.error(f"判断实验归档状态时出错: {e}")
            return False
    
    def _convert_dates_to_strings(self, data: Any) -> Any:
        """
        递归转换数据中的所有date对象为字符串
        
        Args:
            data: 要转换的数据
        
        Returns:
            转换后的数据
        """
        if isinstance(data, dict):
            converted = {}
            for key, value in data.items():
                converted[key] = self._convert_dates_to_strings(value)
            return converted
        elif isinstance(data, list):
            return [self._convert_dates_to_strings(item) for item in data]
        elif isinstance(data, date):
            return data.isoformat()
        else:
            return data
    
    def get_archivable_experiments(self, experiments: List[Dict[str, Any]], 
                                  archive_threshold_days: int = 180) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        获取可归档的实验和需要保留的实验
        
        Args:
            experiments: 实验列表
            archive_threshold_days: 归档阈值天数
        
        Returns:
            (可归档的实验列表, 需要保留的实验列表)
        """
        archivable = []
        to_keep = []
        
        for exp in experiments:
            if self.should_archive_experiment(exp, archive_threshold_days):
                archivable.append(exp)
            else:
                to_keep.append(exp)
        
        return archivable, to_keep
    
    def archive_experiments(self, experiments: List[Dict[str, Any]], 
                           archive_threshold_days: int = 180) -> Tuple[int, int]:
        """
        归档过期实验数据
        
        Args:
            experiments: 实验列表
            archive_threshold_days: 归档阈值天数
        
        Returns:
            (归档的实验数量, 保留的实验数量)
        """
        try:
            # 获取可归档的实验
            archivable, to_keep = self.get_archivable_experiments(experiments, archive_threshold_days)
            
            if not archivable:
                logger.info("没有需要归档的实验数据")
                return 0, len(experiments)
            
            # 加载现有归档数据
            existing_archived = self.load_archived_experiments()
            
            # 添加新的归档数据
            for exp in archivable:
                try:
                    # 添加归档时间戳
                    exp_copy = exp.copy()
                    exp_copy['archived_at'] = date.today().isoformat()
                    exp_copy['archive_reason'] = f"实验结束超过{archive_threshold_days}天"
                    
                    # 确保所有日期字段都是字符串格式，避免JSON序列化错误
                    exp_copy = self._convert_dates_to_strings(exp_copy)
                    
                    existing_archived.append(exp_copy)
                except Exception as e:
                    logger.error(f"处理实验 {exp.get('sample_batch', 'unknown')} 时出错: {e}")
                    continue
            
            # 保存归档数据
            if not self.save_archived_experiments(existing_archived):
                logger.error("保存归档数据失败")
                return 0, len(experiments)
            
            logger.info(f"成功归档 {len(archivable)} 个实验，保留 {len(to_keep)} 个实验")
            return len(archivable), len(to_keep)
            
        except Exception as e:
            logger.error(f"归档实验数据时出错: {e}")
            return 0, len(experiments)
    
    def load_archived_experiments(self) -> List[Dict[str, Any]]:
        """加载归档的实验数据"""
        try:
            if self.archive_file.exists():
                with gzip.open(self.archive_file, 'rt', encoding='utf-8') as f:
                    return json.load(f)
            return []
        except Exception as e:
            logger.error(f"加载归档数据时出错: {e}")
            # 如果加载失败，尝试备份损坏的文件并重新开始
            self._backup_corrupted_archive()
            return []
    
    def _backup_corrupted_archive(self):
        """备份损坏的归档文件"""
        try:
            if self.archive_file.exists():
                # 创建备份文件名
                backup_file = self.archive_file.parent / f"corrupted_archive_{int(time.time())}.json.gz"
                # 移动损坏的文件
                self.archive_file.rename(backup_file)
                logger.warning(f"已备份损坏的归档文件到: {backup_file}")
        except Exception as e:
            logger.error(f"备份损坏的归档文件失败: {e}")
    
    def save_archived_experiments(self, archived_data: List[Dict[str, Any]]) -> bool:
        """保存归档的实验数据"""
        try:
            # 验证数据完整性
            if not isinstance(archived_data, list):
                logger.error("归档数据必须是列表格式")
                return False
            
            # 创建临时文件
            temp_file = self.archive_file.parent / f"temp_archive_{int(time.time())}.json.gz"
            
            # 先保存到临时文件
            with gzip.open(temp_file, 'wt', encoding='utf-8') as f:
                json.dump(archived_data, f, ensure_ascii=False, indent=2)
            
            # 验证临时文件可以正确读取
            try:
                with gzip.open(temp_file, 'rt', encoding='utf-8') as f:
                    test_data = json.load(f)
                if len(test_data) != len(archived_data):
                    raise ValueError("数据长度不匹配")
            except Exception as e:
                logger.error(f"临时文件验证失败: {e}")
                temp_file.unlink(missing_ok=True)
                return False
            
            # 如果验证通过，替换原文件
            if self.archive_file.exists():
                self.archive_file.unlink()
            temp_file.rename(self.archive_file)
            
            logger.info(f"成功保存 {len(archived_data)} 条归档数据")
            return True
            
        except Exception as e:
            logger.error(f"保存归档数据时出错: {e}")
            # 清理临时文件
            temp_file.unlink(missing_ok=True)
            return False
    
    def restore_archived_experiments(self, sample_batch: str = None, 
                                   method_name: str = None, 
                                   date_range: Tuple[date, date] = None) -> List[Dict[str, Any]]:
        """
        从归档中恢复实验数据
        
        Args:
            sample_batch: 样品批号筛选
            method_name: 检测方法筛选
            date_range: 日期范围筛选 (start_date, end_date)
        
        Returns:
            符合条件的归档实验列表
        """
        try:
            archived_data = self.load_archived_experiments()
            filtered_data = []
            
            for exp in archived_data:
                match = True
                
                # 样品批号筛选
                if sample_batch and exp.get('sample_batch') != sample_batch:
                    match = False
                
                # 检测方法筛选
                if method_name and exp.get('method_name') != method_name:
                    match = False
                
                # 日期范围筛选
                if date_range:
                    start_date, end_date = date_range
                    exp_start = date.fromisoformat(exp['start_date']) if isinstance(exp['start_date'], str) else exp['start_date']
                    exp_end = date.fromisoformat(exp['end_date']) if isinstance(exp['end_date'], str) else exp['end_date']
                    
                    if exp_start > end_date or exp_end < start_date:
                        match = False
                
                if match:
                    filtered_data.append(exp)
            
            logger.info(f"从归档中找到 {len(filtered_data)} 条符合条件的实验")
            return filtered_data
            
        except Exception as e:
            logger.error(f"恢复归档数据时出错: {e}")
            return []
    
    def get_archive_stats(self) -> Dict[str, Any]:
        """获取归档统计信息"""
        try:
            archived_data = self.load_archived_experiments()
            
            # 计算归档文件大小
            archive_size = self.archive_file.stat().st_size if self.archive_file.exists() else 0
            archive_size_mb = archive_size / (1024 * 1024)
            
            # 统计归档数据
            total_archived = len(archived_data)
            
            # 按年份统计
            year_stats = {}
            for exp in archived_data:
                if 'start_date' in exp:
                    try:
                        year = exp['start_date'][:4] if isinstance(exp['start_date'], str) else str(exp['start_date'].year)
                        year_stats[year] = year_stats.get(year, 0) + 1
                    except:
                        pass
            
            return {
                'total_archived': total_archived,
                'archive_size_mb': round(archive_size_mb, 2),
                'year_distribution': year_stats,
                'last_archive_date': max([exp.get('archived_at', '') for exp in archived_data], default='')
            }
            
        except Exception as e:
            logger.error(f"获取归档统计信息时出错: {e}")
            return {}


def auto_archive_experiments(experiments: List[Dict[str, Any]], 
                           archive_threshold_days: int = 180) -> Tuple[List[Dict[str, Any]], int]:
    """
    自动归档过期实验数据
    
    Args:
        experiments: 实验列表
        archive_threshold_days: 归档阈值天数
    
    Returns:
        (归档后的实验列表, 归档的实验数量)
    """
    archiver = DataArchiver()
    archived_count, kept_count = archiver.archive_experiments(experiments, archive_threshold_days)
    
    if archived_count > 0:
        # 返回需要保留的实验列表
        _, to_keep = archiver.get_archivable_experiments(experiments, archive_threshold_days)
        return to_keep, archived_count
    
    return experiments, 0


def manual_archive_by_exp_id(experiments: List[Dict[str, Any]], exp_id: int) -> Tuple[List[Dict[str, Any]], int]:
    """
    手动归档指定实验序号的实验
    
    Args:
        experiments: 实验列表
        exp_id: 要归档的实验序号
    
    Returns:
        (归档后的实验列表, 归档的实验数量)
    """
    archiver = DataArchiver()
    
    # 找到指定实验序号的所有实验
    to_archive = []
    to_keep = []
    
    for exp in experiments:
        if exp.get('exp_id') == exp_id:
            to_archive.append(exp)
        else:
            to_keep.append(exp)
    
    if not to_archive:
        return experiments, 0
    
    # 执行归档
    archived_count, _ = archiver.archive_experiments(to_archive, archive_threshold_days=0)  # 强制归档
    
    return to_keep, archived_count


def manual_archive_by_sample_batch(experiments: List[Dict[str, Any]], sample_batch: str) -> Tuple[List[Dict[str, Any]], int]:
    """
    手动归档指定样品批号的实验
    
    Args:
        experiments: 实验列表
        sample_batch: 要归档的样品批号
    
    Returns:
        (归档后的实验列表, 归档的实验数量)
    """
    archiver = DataArchiver()
    
    # 找到指定样品批号的所有实验
    to_archive = []
    to_keep = []
    
    for exp in experiments:
        if exp.get('sample_batch') == sample_batch:
            to_archive.append(exp)
        else:
            to_keep.append(exp)
    
    if not to_archive:
        return experiments, 0
    
    # 执行归档
    archived_count, _ = archiver.archive_experiments(to_archive, archive_threshold_days=0)  # 强制归档
    
    return to_keep, archived_count


def get_archive_statistics() -> Dict[str, Any]:
    """获取归档统计信息"""
    archiver = DataArchiver()
    return archiver.get_archive_stats()
