from pathlib import Path
import re
import sqlite3
from datetime import datetime
import zstandard
from hashlib import md5
import xml.etree.ElementTree as ET
import base64
import random
import pandas as pd
from typing import Any, Iterable, Optional


class SQLiteDB:
    def __init__(self, db_file):
        """初始化时设置数据库文件路径"""
        self.db_file = db_file
        self.conn = None
        self.cursor = None

    def _connect(self):
        """连接数据库（只连接一次）"""
        if self.conn is None:
            self.conn = sqlite3.connect(self.db_file)  # 连接数据库
            self.cursor = self.conn.cursor()           # 创建游标

    def _close(self):
        """关闭数据库连接"""
        if self.cursor:
            self.cursor.close()  # 关闭游标
        if self.conn:
            self.conn.close()    # 关闭数据库连接
            self.conn = None      # 置空连接

    def fetch_all(self, query, params=()):
        """执行查询操作并返回结果"""
        self._connect()  # 确保连接已打开
        self.cursor.execute(query, params)
        result = self.cursor.fetchall()
        return result

    def fetch_one(self, query, params=()):
        """执行查询操作并返回结果"""
        # print(query,params)
        self._connect()  # 确保连接已打开
        self.cursor.execute(query, params)
        result = self.cursor.fetchone()
        return result

    def __del__(self):
        """析构函数，自动关闭连接"""
        self._close()


def str_md5(ss: str) -> str:
    """Calculate the md5 for string"""
    m = md5()
    m.update(ss.encode())
    return m.digest().hex()


def zstd_decompress(data: bytes) -> bytes:
    """Decompress with zstd"""
    zctx = zstandard.ZstdDecompressor()
    return zctx.decompress(data)


def find(dir: str, glob: str) -> list:
    """Scan all files within special directory"""
    root_dir = Path(dir)
    return [item for item in root_dir.rglob(glob) if item.is_file()]

def date_solve(start: str, end: str) -> list:
    '''日期处理'''
    if re.match(r'^[0-9]{4}-[0-9]{2}-[0-9]{2}$', start):
        start = int(datetime.strptime(start,'%Y-%m-%d').timestamp())
    elif re.match(r'^[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}$', start):
        start = int(datetime.strptime(start,'%Y-%m-%d %H:%M:%S').timestamp())
    else:
        start = None

    if re.match(r'^[0-9]{4}-[0-9]{2}-[0-9]{2}$', end):
        end = int(datetime.strptime(end,'%Y-%m-%d').timestamp())
    elif re.match(r'^[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}$', end):
        end = int(datetime.strptime(end,'%Y-%m-%d %H:%M:%S').timestamp())
    else:
        end = None
    
    return (start,end)

#regex msg处理
def msg_solve(msgs:list):
    result = []
    for item in msgs:
        if isinstance(item[-1], str):
            item[-1] = item[-1].encode()

        if item[-1][:4] == b"\x28\xb5\x2f\xfd":
            item[-1] = zstd_decompress(item[-1])

        msg_prefix = f"{item[1]}:\n".encode()

        if item[-1][:len(msg_prefix)] != msg_prefix:
            item[-1] = msg_prefix + item[-1]
        if item[0] == 3:
            item[-1] = item[-1].split()[0] + "\n[图片消息]".encode()
            item[-1] = item[-1].split()[0] + "\n[图片消息]".encode()
        if item[0] == 43:
            item[-1] = item[-1].split()[0] + "\n[视频消息]".encode()
        if item[0] == 73014455032:
            item[-1] = item[-1].split()[0] + "\n[位置共享]".encode()
        if item[0] in (47, 25769803825, 21474836529, 244813135921, 154618822705, 17179869233, ):
            xml_msg = b"\n".join(item[-1].split(b"\n")[1:])
            xml_msg = (b'<' + b':<'.join(xml_msg.split(b':<')[1:])) if len(xml_msg.split(b':<')) > 1 else xml_msg
            xml_msg = xml_msg.split(b'/msg>')[0] + b'/msg>'
            
            if xml_msg[:6] != b"<?xml ":
                xml_msg = b"<?xml version='1.0' encoding='utf-8'?>\n" + xml_msg
            xml_msg = xml_msg.strip(b"\x00")
            parser = ET.XMLParser(encoding="utf-8")
            try:
                root = ET.fromstring(xml_msg, parser=parser)
            except:
                print(f"[-] Failed to parse message: {xml_msg}")
                continue
            if b"<msg><emoji " in item[-1] or b"<msg><emoji" in item[-1].replace(b"\n", b"").replace(b" ", b""):
                emoji_desc = root.find('emoji').get('desc')
                if not emoji_desc is None and emoji_desc != "":
                    emoji_desc = base64.b64decode(emoji_desc)
                    if b"zh_cn\x12" in emoji_desc:
                        tmp = emoji_desc.split(b"zh_cn\x12")[1]
                        cap_len = tmp[0]
                        if cap_len > 0:
                            cap = tmp[1:1+cap_len]
                            item[-1] = item[-1].split()[0] + "\n[动画表情]".encode() + cap
                            # continue
                    elif b"zh_tw\x12" in emoji_desc:
                        tmp = emoji_desc.split(b"zh_tw\x12")[1]
                        cap_len = tmp[0]
                        if cap_len > 0:
                            cap = tmp[1:1+cap_len]
                            item[-1] = item[-1].split()[0] + "\n[动画表情]".encode() + cap
                            # continue
                    elif b"default\x12" in emoji_desc:
                        tmp = emoji_desc.split(b"default\x12")[1]
                        cap_len = tmp[0]
                        if cap_len > 0:
                            cap = tmp[1:1+cap_len]
                            item[-1] = item[-1].split()[0] + \
                                "\n[动画表情]".encode() + cap
                            # continue
                    
                else:
                    emoji_attr = root.find('emoji').get('emojiattr')
                    if not emoji_attr is None and emoji_attr != "":
                        emoji_attr = base64.b64decode(emoji_attr)
                        cap_len = emoji_attr[1]
                        cap = emoji_attr[2:2+cap_len]
                        item[-1] = item[-1].split()[0] + "\n[动画表情]".encode() + cap
                    else:
                        # print(xml_msg)
                        item[-1] = item[-1].split()[0] + "\n[动画表情]".encode()

            else:
                try:
                    prefix = "[卡片消息]"
                    if item[0] == 244813135921:
                        prefix = ""
                    if item[0] == 25769803825:
                        prefix = "[文件消息]"
                    if item[0] == 154618822705:
                        prefix = "[小程序卡片消息]"
                    item[-1] = item[-1].split()[0] + f"\n{prefix}".encode() + root.find('appmsg').find('title').text.encode()
                    if item[0] in (17179869233, 21474836529):
                        item[-1] = item[-1] + b" "  + root.find('appmsg').find('url').text.encode()
                except Exception as e:
                    print('[未知消息类型]',item[-1], e)
                    item[-1] = msg_prefix + '[未知消息类型]'.encode()

        item[-1] = item[-1].replace(msg_prefix, b"")

        result.append(item)
    return msgs

class WeixinDbStorage:
    def __init__(self):
        self.msg_db = SQLiteDB(find('./msg', 'merged.db')[0])
        self.contact_db = SQLiteDB(find('.', 'contact.db')[0])
        self.msgtype = '1, 3, 43, 47, 48, 10000, 25769803825, 21474836529, 244813135921, 154618822705, 17179869233, 73014455032'
    
    def get_first_time_of_message(self, username: str):
        """获取指定用户名的最早一条消息和时间戳"""
        sql = "SELECT strftime('%Y-%m-%d %H:%M:%S',create_time,'unixepoch','localtime') as StrTime, message_content FROM merged_msg WHERE username = ? ORDER BY create_time ASC LIMIT 1"
        result = self.msg_db.fetch_one(sql, (username,))
        return result if result else []
    
    def get_last_time_of_message2(self, username: str):
        """获取指定用户名的最后一条消息和时间戳"""
        sql = "SELECT strftime('%Y-%m-%d %H:%M:%S',create_time,'unixepoch','localtime') as StrTime, message_content FROM merged_msg WHERE username = ? ORDER BY create_time DESC LIMIT 1"
        result = self.msg_db.fetch_one(sql, (username,))
        return result if result else []
    
    def get_contact_by_username(self, username: str) -> list:
        """通过用户名获取联系人信息"""
        sql = "SELECT username, alias, local_type, remark, nick_name, small_head_url, extra_buffer FROM contact WHERE username = ?"
        result = self.contact_db.fetch_one(sql, (username,))

        return list(result) if result else None
    
    def get_contact_by_usernames(self, usernames: list[str]=[]) -> pd.DataFrame | None:
        """通过用户名批量获取联系人信息,不输入则返回所有记录
            返回字典 {用户名: [用户名, 别名, 本地类型, 备注, 昵称, 小头像URL, 额外缓冲区]}"""
        placeholders = ', '.join(['?'] * len(usernames))
        sql = f'''
                SELECT username, alias, local_type, remark, nick_name, small_head_url, extra_buffer 
                FROM contact 
                WHERE username IN ({placeholders})
            '''
        results = self.contact_db.fetch_all(sql, tuple(usernames))

        if results:
            df = pd.DataFrame(results, columns=['username', 'alias', 'local_type', 'remark', 'nickname', 'small_head_url', 'extra_buffer'])
            return df
        return None
    
    def get_all_usernames_matching_encrypt(self) -> list:
        """返回所有 username 等于 encrypt_username 的记录"""
        sql = "SELECT username FROM contact WHERE username = encrypt_username"
        results = self.contact_db.fetch_all(sql)
        return [row[0] for row in results] if results else []
    
    def get_usernames_by_nicknames(self, nicknames: list[str]=[]) -> pd.DataFrame | None:
        """ 通过多个昵称批量获取用户名映射
            昵称为空则返回所有记录
            返回df = [用户名, 昵称, 备注, 小头像URL]
        """
        # 生成 IN 子句的占位符 (?,?,...?)
        placeholders = ', '.join(['?'] * len(nicknames))
        
        # 查询昵称和用户名的映射关系
        sql = f"""
            SELECT username, nick_name, remark, small_head_url
            FROM contact 
            {f'WHERE nick_name IN ({placeholders})' if nicknames else ''}
        """
        if nicknames:
            results = self.contact_db.fetch_all(sql, tuple(nicknames))
            print('results', results)
        else:
            results = self.contact_db.fetch_all(sql)

        if results:
            df = pd.DataFrame(results, columns=['username', 'nickname', 'remark', 'small_head_url'])
            return df
        return None
    
    def get_msg_count_by_username(self, username: str = '', start: str = '', end: str='') -> int:
        """获取指定username的聊天消息总数"""
        start_time, end_time = date_solve(start, end)
        
        sql = f"""
            SELECT COUNT(*) FROM merged_msg 
            WHERE username = ? 
            AND local_type IN ({self.msgtype}) 
            {'AND create_time>' + str(start_time) if start else ''}
            {'AND create_time<' + str(end_time) if end else ''}
        """
        result = self.msg_db.fetch_one(sql, (username,))
        return result[0] if result else 0

    def get_message_length(self, username='', start: str = '', end: str = '', sender=''):
        """获取消息长度
            start, end 为时间范围,格式为 '2023-01-01'或'2023-01-01 00:00:00'
            不输入用户名则获取所有用户发送的文本消息长度
        """
        start_time, end_time = date_solve(start, end)

        sql = f'''
            select sum(length(message_content))
            from merged_msg
            where local_type=1
            {'and username=' + f"'{username}'" if username else ''}
            {'AND sender_name="{sender}"' if sender else ''}
            {'AND create_time>' + str(start_time) if start else ''}
            {'AND create_time<' + str(end_time) if end else ''}
        '''
        result = self.msg_db.fetch_one(sql)
        
        return result[0] if result[0] else 0
    
    def get_send_messages_number_sum(self, username='', start: str = '', end: str = ''):
        """获取发送消息总数
            start, end 为时间范围,格式为 '2023-01-01'或'2023-01-01 00:00:00'
            不输入用户名则获取所有用户发送消息总数
        """
        # myusername = self.get_all_usernames_matching_encrypt()
        start, end = date_solve(start=start, end=end)

        sql = f'''
            select count(*)
            from merged_msg
            {'where sender_name=' + f"'{username}'" if username else ''}
            {'AND create_time > ' + str(start) if start else '' }
            {'AND create_time < ' + str(end) if end else ''}
        '''
        result = self.msg_db.fetch_one(sql)
        total_msg = result[0] if result else 0
        
        return total_msg
    
    def get_chatroom_msg(self, username, start: str = '', end: str = ''):
        """获取群聊消息数量统计，按发送人分组统计
            start, end 为时间范围,格式为 '2023-01-01'或'2023-01-01 00:00:00'
            也可以用于聊天中统计两人的消息数量
            返回 [(sender_name, count(*))]
        """
        start, end = date_solve(start=start, end=end)

        sql = f'''
            select sender_name, count(*)
            from merged_msg
            where username = ?
            {'AND create_time > ' + str(start) if start else '' }
            {'AND create_time < ' + str(end) if end else ''}
            group by sender_name
        '''
        result = self.msg_db.fetch_all(sql,(username,))
        return result if result else []
    
    def get_messages_by_keyword(self, username_, keyword, num=5, max_len=10, start: str = '', end: str = '', year_='all'):
        """通过关键词获取聊天记录"""

        start, end = date_solve(start=start, end=end)

        sql = f'''
            select local_id, real_sender_id, create_time, message_content, strftime('%Y-%m-%d %H:%M:%S',create_time,'unixepoch','localtime') as StrTime
            from merged_msg
            where username=? and local_type=1 and LENGTH(message_content)<? and message_content like ?
            {'AND create_time > ' + str(start) if start else '' }
            {'AND create_time < ' + str(end) if end else ''}
            order by create_time desc
        '''
        
        messages = self.msg_db.fetch_all(sql, (username_, max_len, f'%{keyword}%'))
        if len(messages) > 5:
            messages = random.sample(messages, num)
        temp = []
        for msg in messages:
            time_s = msg[2]
            is_send = msg[1]
            sql = '''
                select local_id, real_sender_id, create_time, message_content, strftime('%Y-%m-%d %H:%M:%S',create_time,'unixepoch','localtime') as StrTime
                from merged_msg
                where create_time > ? and username=? and local_type=1 and real_sender_id != ?
                order by create_time ASC
                limit 1
            '''
            next_msg = self.msg_db.fetch_one(sql, (time_s, username_, is_send))
            temp.append((msg, next_msg))
        res = []
        for dialog in temp:
            msg1 = dialog[0]
            msg2 = dialog[1]
            try:
                res.append((
                    (msg1[1], msg1[2], msg1[3].split(keyword), msg1[4]),
                    (msg2[1], msg2[2], msg2[3].split(':\n')[-1], msg2[4])
                ))
            except TypeError:
                res.append((
                    ('', '', ['', ''], ''),
                    ('', '', '', '')
                ))
        
        return res
    
    def get_messages_by_hour(self, username_, start: str = '', end: str = '', year_='all'):
        '''获取按小时统计聊天数量'''
        start, end = date_solve(start=start, end=end)

        sql = f'''
            select strftime('%H',create_time,'unixepoch','localtime') as Hour, count(*) as Num
            from (select message_content,create_time
                from merged_msg
                where username=?
                {'AND create_time > ' + str(start) if start else '' }
                {'AND create_time < ' + str(end) if end else ''}
                )
            group by Hour
            '''
        result = self.msg_db.fetch_all(sql, (username_,))
        return result if result else []
    
    def get_latest_time_of_message(self, username_: str, start: str = '', end: str = '', year_='all'):
        '''获取最新消息时间'''
        # username_md5 = str_md5(username_)
        start, end = date_solve(start=start, end=end)

        sql = f'''
                SELECT sender_name, message_content,
                    strftime('%Y-%m-%d %H:%M:%S', create_time, 'unixepoch', 'localtime') as StrTime,
                    strftime('%H:%M:%S', create_time, 'unixepoch', 'localtime') as hour
                FROM merged_msg
                WHERE local_type=1 AND username=?
                    AND strftime('%H:%M:%S', create_time, 'unixepoch', 'localtime') BETWEEN '00:00:00' AND '05:00:00'
                    {'AND create_time > ' + str(start) if start else '' }
                    {'AND create_time < ' + str(end) if end else ''}
                ORDER BY hour DESC
                LIMIT 20;
            '''
        result = self.msg_db.fetch_all(sql, (username_,))
        
        res = []
        if len(result) > 2:
            res.append(result[0])
            is_sender = result[0][0]
            for msg in result[1:]:
                if msg[0] != is_sender:
                    res.append(msg)
                    break
        
        return res
    
    def get_messages_by_month(self, username_: str, start: str = '', end: str = '', year_='all'):
        '''按username获取月份聊天数量统计'''
        
        start, end = date_solve(start=start, end=end)
        
        sql = f'''
            SELECT strftime('%Y-%m',create_time,'unixepoch','localtime') as month, count(message_content)
            from (
                SELECT message_content, create_time
                FROM merged_msg
                WHERE username = ?
                {'AND create_time > ' + str(start) if start else '' }
                {'AND create_time < ' + str(end) if end else ''}
            )
            group by month
        '''
        result = self.msg_db.fetch_all(sql, (username_,))
        return result if result else []
    
    def get_msg_list_by_username(self, username: str='', start: str = '', end: str = '', type = None) -> list:
        """通过用户名获取聊天记录 返回list[local_type, sender_name, create_time, message_content]"""
        '''
        1               文本消息
        3               图片消息
        34              语音消息
        42              名片消息
        43              视频消息
        47              第三方动画表情
        48              位置消息
        244813135921    引用消息
        17179869233     卡片式链接（带描述）
        21474836529     卡片式链接
        154618822705    小程序分享
        12884901937     音乐卡片
        8594229559345   红包卡片
        81604378673     聊天记录合并转发消息
        266287972401    拍一拍消息
        8589934592049   转账卡片
        270582939697    视频号直播卡片
        25769803825     文件消息
        10000           系统消息（撤回、加入群聊、群管理、群语音通话等）
        '''
        start, end = date_solve(start=start, end=end)

        sql = f"""SELECT local_type, sender_name, create_time, message_content 
                FROM merged_msg 
                WHERE local_type IN ({self.msgtype if type is None else type})
                {'AND username = ' + f"'{username}'" if username else ''}
                {'AND create_time > ' + str(start) if start else '' }
                {'AND create_time < ' + str(end) if end else ''}
                ORDER BY create_time ASC
            """
        result = self.msg_db.fetch_all(sql)
        result = [list(item) for item in result]
        result = msg_solve(result)
        result = [item for item in result if not (item[-1] is None or (
            len(item[-1].split(b"\n")) > 5 and "群聊总结" in item[-1].split(b"\n")[1].decode()))]
        return result
    
    def get_messages_by_days(self,username_,start: str, end: str):
        '''获取日期聊天数量, 按天统计返回list[days, count]'''
        start, end = date_solve(start=start, end=end)
        
        sql = f'''
            SELECT strftime('%Y-%m-%d',create_time,'unixepoch','localtime') as days,count(message_content)
            from (
                SELECT message_content, create_time
                FROM merged_msg 
                WHERE username = ?
                {'AND create_time > ' + str(start) if start else '' }
                {'AND create_time < ' + str(end) if end else ''}
            )
            group by days
        '''
        resullt = self.msg_db.fetch_all(sql, (username_,))
        return resullt if resullt else []
    
    def get_chatted_top_contacts(self, top_n: int, start: str ='', end: str='', contain_chatroom: bool = False) -> list:
        """
        获取聊天记录最多的topN个联系人,默认不统计群聊
        返回一个列表，[用户名，value] 为该用户在指定时间区间内的消息总数。
        """
        start, end = date_solve(start=start, end=end)

        sql = f"""
            SELECT username, Count(message_content)
            FROM merged_msg
            WHERE username != "filehelper" and username != "notifymessage" and username != "qqmail" and username not like "gh_%" and username not like "%@openim"
            {"AND username not like '%@chatroom'" if not contain_chatroom else ""}
            {'AND create_time > ' + str(start) if start else '' }
            {'AND create_time < ' + str(end) if end else ''}
            group by username
            order by Count(message_content) desc
            limit ?
        """
        results = self.msg_db.fetch_all(sql, (top_n,))
        return results if results else []
    
    def get_msg_list_by_username_paged(self, username: str, start: str = '', end: str = '', page: int = 1, per_page: int = 100, type=None) -> list:
        """分页查询消息指定username的消息列表"""
        start, end = date_solve(start=start, end=end)

        offset = (page - 1) * per_page
        sql = f'''
                SELECT local_type, sender_name, create_time, message_content 
                FROM merged_msg 
                WHERE local_type IN ({self.msgtype if type is None else type})
                {'AND username = ' + f"'{username}'" if username else ''}
                {'AND create_time > ' + str(start) if start else '' }
                {'AND create_time < ' + str(end) if end else ''}
                ORDER BY create_time ASC
                LIMIT ? OFFSET ?
            '''

        result = self.msg_db.fetch_all(sql, (per_page, offset))
        result = [list(item) for item in result]
        result = msg_solve(result)
        result = [item for item in result if not (item[-1] is None or (
            len(item[-1].split(b"\n")) > 5 and "群聊总结" in item[-1].split(b"\n")[1].decode()))]
        return result
    
if __name__ == "__main__":
    group_name = ["123"]
    start = "2015-12-18"
    end = "2025-12-19"
    wx = WeixinDbStorage()
    # username_list = wx.get_usernames_by_nicknames(group_name)
    # print(f"[+] The username of the group {group_name} is {username_list[0][1]}")
    # # msg = wx.get_msg_list_by_username_paged(username_list[0][1], start, end, 1, 10)
    # msg_list = wx.get_msg_list_by_username(username_list[0][1], start, end)
    # msg = [[item[1], item[-1].decode(errors='ignore')] for item in msg_list][-20:-10]
    # print(msg)
    ss = wx.get_usernames_by_nicknames()
    print(ss)

        
    
