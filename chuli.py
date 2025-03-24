
import sqlite3
import os
import hashlib
from pathlib import Path

# 全局变量存储进度
current_progress = 0
total_progress = 100

class DatabaseMerger:
    def __init__(self, merged_db="merged.db", contact_db="contact.db"):
        self.merged_db = merged_db
        self.contact_db = contact_db
        self.batch_size = 10000  # 根据内存调整批次大小
        
        # 初始化目标数据库
        with self._connect(self.merged_db) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS merged_msg (
                    source_table TEXT,
                    local_id INTEGER,
                    server_id INTEGER,
                    local_type INTEGER,
                    sort_seq INTEGER,
                    real_sender_id INTEGER,
                    create_time INTEGER,
                    status INTEGER,
                    upload_status INTEGER,
                    download_status INTEGER,
                    server_seq INTEGER,
                    origin_source INTEGER,
                    source TEXT,
                    message_content TEXT,
                    compress_content TEXT,
                    packed_info_data BLOB,
                    WCDB_CT_message_content INTEGER,
                    WCDB_CT_source INTEGER,
                    sender_name TEXT,
                    source_md5 TEXT GENERATED ALWAYS AS (
                        CASE WHEN instr(source_table, '_') > 0 
                        THEN substr(source_table, instr(source_table, '_')+1) 
                        ELSE NULL END
                    ) VIRTUAL,
                    username TEXT,
                    remark TEXT,
                    nick_name TEXT
                )
            ''')
            conn.execute("CREATE INDEX IF NOT EXISTS idx_md5 ON merged_msg(source_md5)")
            conn.commit()

    def _connect(self, db_path, optimze=False):
        """创建数据库连接"""
        conn = sqlite3.connect(db_path)
        if optimze:
            conn.execute("PRAGMA synchronous = OFF")
            conn.execute("PRAGMA journal_mode = MEMORY")
            conn.execute("PRAGMA cache_size = -10000")  # 10MB缓存
        return conn

    def _get_name_mapping(self, conn):
        """获取Name2Id映射表"""
        try:
            return dict(conn.execute("SELECT rowid, user_name FROM Name2Id").fetchall())
        except sqlite3.OperationalError:
            return {}

    def merge_sources(self, source_dirs, table_pattern="Msg_%"):
        """合并源数据库"""
        global current_progress
        current_progress = 0
        
        # 收集所有源数据库
        source_dbs = []
        for dir_path in source_dirs:
            source_dbs.extend(Path(dir_path).rglob("message_?.db"))
        
        total_dbs = len(source_dbs)
        if total_dbs == 0:
            return
            
        progress_per_db = 70 / total_dbs  # 数据库合并占70%的进度
        
        # 分批处理每个数据库
        with self._connect(self.merged_db, optimze=True) as dest_conn:
            dest_cur = dest_conn.cursor()
            
            for db_index, db_path in enumerate(source_dbs):
                if not db_path.exists():
                    continue
                
                with self._connect(db_path) as src_conn:
                    # 获取姓名映射
                    name_map = self._get_name_mapping(src_conn)
                    
                    # 处理消息表
                    tables = [
                        t[0] for t in 
                        src_conn.execute(
                            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE ?",
                            (table_pattern,)
                        )
                    ]
                    
                    for table_index, table in enumerate(tables):
                        try:
                            src_cur = src_conn.cursor()
                            src_cur.execute(f'''
                                SELECT 
                                    local_id, server_id, local_type, sort_seq, real_sender_id,
                                    create_time, status, upload_status, download_status, server_seq,
                                    origin_source, source, message_content, compress_content,
                                    packed_info_data, WCDB_CT_message_content, WCDB_CT_source
                                FROM {table}
                            ''')
                            
                            insert_buffer = []
                            while True:
                                rows = src_cur.fetchmany(self.batch_size)
                                if not rows:
                                    break
                                
                                # 添加附加字段
                                processed = [
                                    (
                                        table,  # source_table
                                        *row,
                                        name_map.get(row[4], None),  # sender_name
                                    )
                                    for row in rows
                                ]
                                
                                insert_buffer.extend(processed)
                                if len(insert_buffer) >= self.batch_size:
                                    dest_cur.executemany('''
                                        INSERT INTO merged_msg (
                                            source_table, local_id, server_id, local_type,
                                            sort_seq, real_sender_id, create_time, status,
                                            upload_status, download_status, server_seq,
                                            origin_source, source, message_content,
                                            compress_content, packed_info_data,
                                            WCDB_CT_message_content, WCDB_CT_source,
                                            sender_name
                                        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                                    ''', insert_buffer)
                                    dest_conn.commit()
                                    insert_buffer.clear()
                            
                            if insert_buffer:
                                dest_cur.executemany('''
                                    INSERT INTO merged_msg (
                                        source_table, local_id, server_id, local_type,
                                        sort_seq, real_sender_id, create_time, status,
                                        upload_status, download_status, server_seq,
                                        origin_source, source, message_content,
                                        compress_content, packed_info_data,
                                        WCDB_CT_message_content, WCDB_CT_source,
                                        sender_name
                                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                                ''', insert_buffer)
                                dest_conn.commit()
                        
                        except sqlite3.Error as e:
                            print(f"Error processing {table}: {str(e)}")
                
                # 更新进度
                current_progress = int((db_index + 1) * progress_per_db)

    def update_contacts(self):
        """更新联系人信息"""
        global current_progress
        
        # 预加载联系人数据
        contact_map = {}
        with self._connect(self.contact_db) as conn:
            try:
                for username, remark, nick_name in conn.execute(
                    "SELECT username, remark, nick_name FROM Contact"
                ):
                    md5 = hashlib.md5(username.encode()).hexdigest()
                    contact_map[md5] = (username, remark, nick_name)
            except sqlite3.OperationalError:
                return
        
        # 分批更新
        with self._connect(self.merged_db, optimze=True) as conn:
            conn.execute("BEGIN")
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT rowid, source_md5 FROM merged_msg")
                
                total_rows = cursor.fetchall()
                progress_per_batch = 30 / (len(total_rows) / self.batch_size)  # 联系人更新占30%的进度
                
                update_buffer = []
                for batch_index, (rowid, md5) in enumerate(total_rows):
                    if md5 in contact_map:
                        update_buffer.append((*contact_map[md5], rowid))
                    
                    if len(update_buffer) >= self.batch_size:
                        conn.executemany('''
                            UPDATE merged_msg 
                            SET username=?, remark=?, nick_name=?
                            WHERE rowid=?
                        ''', update_buffer)
                        update_buffer.clear()
                        # 更新进度
                        current_progress = 70 + int((batch_index / len(total_rows)) * 30)
                
                if update_buffer:
                    conn.executemany('''
                        UPDATE merged_msg 
                        SET username=?, remark=?, nick_name=?
                        WHERE rowid=?
                    ''', update_buffer)
                
                conn.commit()
                current_progress = 100
            except Exception as e:
                conn.rollback()
                raise e

def find(dir: str, glob: str) -> list:
    """Scan all files within special directory"""
    root_dir = Path(dir)
    return [item for item in root_dir.rglob(glob) if item.is_file()]

def get_current_progress():
    """获取当前进度"""
    global current_progress
    return current_progress

def main():
    try:
        contact_db_fp = find(".", "contact.db")
        if contact_db_fp and find(".", "message_?.db"):
            merger = DatabaseMerger('msg/merged.db',contact_db_fp[0])
        
            # Step 1: 合并数据
            merger.merge_sources(
                source_dirs='.',  # 包含源数据库的目录
                table_pattern="Msg_%"
            )
            
            # Step 2: 更新联系人信息
            merger.update_contacts()
        else:
            return False
        
        return True
    except:
        return False

if __name__ == "__main__":
    contact_db_fp = find(".", "contact.db")

    if contact_db_fp and find(".", "message_?.db"):
        merger = DatabaseMerger('msg/merged.db',contact_db_fp[0])
        
        # Step 1: 合并数据
        merger.merge_sources(
            source_dirs='.',  # 包含源数据库的目录
            table_pattern="Msg_%"
        )
        
        # Step 2: 更新联系人信息
        merger.update_contacts()