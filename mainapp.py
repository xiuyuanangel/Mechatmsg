"""
微信聊天记录分析Web应用主程序

本模块实现了一个基于Flask的Web应用,用于分析微信聊天记录。
主要功能包括:
1. 微信数据库解密
2. 聊天记录查看
3. 数据统计分析
4. 可视化图表展示
"""

from datetime import datetime
import re
import os
import shutil
import subprocess
from typing import List, Tuple, Dict, Optional

from flask import Flask, jsonify, render_template, request, redirect, url_for
import pandas as pd
import numpy as np

import getwxdata as gmt
from chuli import get_current_progress, main, find
import analysis

# 创建数据库目录
if not os.path.exists("./db"):
    os.mkdir("./db")

app = Flask(__name__)
app.config['myusername'] = ''

# 全局进度变量
_progress = 0

def get_myusername() -> Optional[str]:
    """获取当前用户的微信ID
    
    Returns:
        str: 当前用户的微信ID,如果获取失败则返回None
    """
    wx = gmt.WeixinDbStorage()
    myusername = wx.get_all_usernames_matching_encrypt()
    return myusername[0] if myusername and myusername[0]!='' else None

@app.route('/')
def index():
    """首页路由
    
    展示联系人列表,如果数据未解密则重定向到解密页面
    """
    try:
        app.config['myusername'] = get_myusername()
        wx = gmt.WeixinDbStorage()
        df = wx.get_usernames_by_nicknames()
        if df.empty:
            return redirect(url_for('decrypt'))
        return render_template('index2.html', 
                             contacts=zip(df['nickname'], df['username'], 
                                       df['small_head_url'], df['remark']),
                             myname=app.config['myusername'] if app.config['myusername'] else get_myusername())
    except:
        return redirect(url_for('decrypt'))

@app.route('/get_progress')
def get_progress():
    """获取解密进度
    
    Returns:
        dict: 包含进度信息的JSON响应
    """
    if _progress == 0:
        return jsonify({'progress': 0})
    return jsonify({'progress': get_current_progress()})

@app.route('/check_decrypted_data')
def check_decrypted_data():
    """检查解密数据状态
    
    检查数据库文件是否存在及解密状态
    
    Returns:
        dict: 包含检查结果的JSON响应
    """
    dblist = os.listdir("./db")
    exists = os.path.exists('msg/merged.db')
    if dblist and exists:
        return jsonify({'exists': True, 'dblist': dblist})
    elif dblist and not exists:
        return jsonify({'exists': False, 'dblist': dblist})
    else:
        return jsonify({'exists': False, 'dblist': dblist})

@app.route('/start_decrypt', methods=['POST']) 
def start_decrypt():
    """启动数据解密过程
    
    使用wechat-dump-rs工具解密微信数据库
    
    Returns:
        dict: 包含解密结果的JSON响应
    """
    global _progress
    try:
        # 获取现有数据库文件列表
        dblist = os.listdir("./db")
        
        # 调用解密工具
        p = subprocess.Popen(["./bin/wechat-dump-rs.exe", "-a" ,"-o", ".\db"], 
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = p.communicate()
        
        # 检查错误
        if err:
            if "WeChat is not running" in err.decode("utf-8"):
                return jsonify({'success': False, 'error': "微信未运行"})
            return jsonify({'success': False, 'error': err.decode("utf-8")})
            
        # 清理旧文件
        for db in dblist:
            folder_path = f"./db/{db}"
            print("删除文件夹", folder_path)
            shutil.rmtree(folder_path)
            
        if os.path.exists('msg/merged.db'):
            os.remove("msg/merged.db")
        
        # 启动解密
        contact_db_fp = find(".", "contact.db")
        if contact_db_fp and find(".", "message_?.db"):
            _progress = 1
            if main():
                return jsonify({'success': True})
            return jsonify({'success': False, 'error': "解密失败"})
        
        return start_decrypt()
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/decrypt', methods=['GET', 'POST'])
def decrypt():
    """解密页面路由
    
    GET: 显示解密页面
    POST: 执行解密操作
    """
    if request.method == 'GET':
        return render_template('decrypt.html')
    elif request.method == 'POST':
        main()
        return redirect(url_for('index'))

@app.route('/get_message', methods=['POST'])
def get_message():
    """获取聊天记录
    
    按页获取指定用户的聊天记录
    
    Returns:
        dict: 包含消息数据的JSON响应
    """
    username = request.json["username"]
    page = request.json.get("page", 1)  # 默认第一页
    per_page = request.json.get("per_page", 100)  # 默认每页100条
    
    wx = gmt.WeixinDbStorage()
    try:
        # 获取总消息数
        total_msg = wx.get_msg_count_by_username(username)
        if total_msg/per_page + 1 <= page:
            return jsonify([])
            
        # 分页获取消息
        msg_list = wx.get_msg_list_by_username_paged(username, '', '', page, per_page)
        msg_content_list = [[item[1],item[-1].decode(errors='ignore'), item[-2]] 
                          for item in msg_list]

        # 获取联系人信息
        df = wx.get_contact_by_usernames(list(set([username for username, msg, t in msg_content_list])))
        df['显示名'] = np.where(df['remark']!='', df['remark'], df['nickname'])
        # print(df)
        # 整理消息数据
        datas = [[username, msg, df[df['username'] == username]['显示名'].values[0] if username else '系统', t] 
                for username, msg, t in msg_content_list]
        # datas = []
        # for username, msg, t in msg_content_list:
        #     try:
        #         datas.append([username, msg, df[df['username'] == username]['显示名'].values[0] if username else '系统', t])
        #     except:
        #         print('信息',username, msg, t)
        #         print(df[df['username'] == username]['显示名'].values)
        
        return jsonify({
            "data": datas,
            "total": total_msg,
            "page": page,
            "per_page": per_page
        })
        
    except Exception as e:
        print(e)
        return jsonify([])

def decode_extra_buf(extra_buf_content: bytes) -> Dict:
    """解析联系人额外信息
    
    Args:
        extra_buf_content: 包含额外信息的字节串
        
    Returns:
        dict: 解析后的联系人信息
    """
    if not extra_buf_content:
        return {
            "region": ('', '', ''),
            "signature": '',
            "telephone": '',
            "gender": 0,
        }
        
    # 定义信息类型标识
    trunk_name = {
        b"\x46\xCF\x10\xC4": "个性签名",
        b"\xA4\xD9\x02\x4A": "国家",
        b"\xE2\xEA\xA8\xD1": "省份",
        b"\x1D\x02\x5B\xBF": "市",
        b"\x75\x93\x78\xAD": "手机号",
        b"\x74\x75\x2C\x06": "性别",
    }
    
    res = {"手机号": ""}
    off = 0
    
    try:
        # 解析各类型信息
        for key, trunk_head in trunk_name.items():
            try:
                off = extra_buf_content.index(key) + 4
            except:
                continue
                
            char = extra_buf_content[off: off + 1]
            off += 1
            
            if char == b"\x04":  # 4字节整数
                int_content = extra_buf_content[off: off + 4]
                off += 4
                int_content = int.from_bytes(int_content, "little")
                res[trunk_head] = int_content
                
            elif char == b"\x18":  # UTF-16字符串
                length = extra_buf_content[off: off + 4]
                off += 4
                length = int.from_bytes(length, "little")
                content = extra_buf_content[off: off + length]
                off += length
                res[trunk_head] = content.decode("utf-16").rstrip("\x00")
                
        return {
            "region": (res.get("国家",""), res.get("省份",""), res.get("市","")),
            "signature": res.get("个性签名",""),
            "telephone": res.get("手机号",""),
            "gender": res.get("性别",0),
        }
        
    except:
        return {
            "region": ('', '', ''),
            "signature": '',
            "telephone": '',
            "gender": 0,
        }

def new_decode_extra_buf(extra_buf_content: bytes) -> Dict:
    """新版本联系人额外信息解析
    
    Args:
        extra_buf_content: 包含额外信息的字节串
        
    Returns:
        dict: 解析后的联系人信息
    """
    if not extra_buf_content:
        return {
            "region": ('', '', ''),
            "signature": '',
            "telephone": '',
            "gender": 0,
        }
        
    res = {
        "手机号": "",
        "性别":extra_buf_content[1]
    }
    
    # 定义分隔符
    separators = [b'\x18\x00\x22',b'\x2a',b'2',b':',b'@']
    positions = []
    
    # 获取各字段位置
    for i in range(len(separators)-1):
        try:
            start = extra_buf_content.index(separators[i]) + len(separators[i]) + 1
            end = extra_buf_content.index(separators[i+1])
            positions.append([start, end])
        except:
            positions.append([0,0])
    
    # 解析各字段内容
    field_names = ["个性签名","国家","省份","市"]
    for i, pos in enumerate(positions):
        try:
            res[field_names[i]] = extra_buf_content[pos[0]:pos[1]].decode(errors='ignore')
        except:
            pass
    
    return {
        "region": (res.get("国家",""), res.get("省份",""), res.get("市","")),
        "signature": res.get("个性签名",""),
        "telephone": res.get("手机号",""),
        "gender": res.get("性别",0),
    }

class Contact:
    """联系人类
    
    存储和处理单个联系人的信息
    """
    
    def __init__(self, contact_info: dict):
        """初始化联系人信息
        
        Args:
            contact_info: 包含联系人信息的字典
        """
        self.wxid = contact_info.get('UserName')
        self.remark = contact_info.get('Remark')
        self.alias = contact_info.get('Alias')
        self.nickName = contact_info.get('NickName')
        
        if not self.remark:
            self.remark = self.nickName
        self.remark = re.sub(r'[\\/:*?"<>|\s\.]', '_', self.remark)
        
        self.smallHeadImgUrl = contact_info.get('smallHeadImgUrl')
        self.smallHeadImgBLOG = b''
        self.is_chatroom = '@chatroom' in self.wxid
        self.detail: dict = contact_info.get('detail', {})

class ContactDefault:
    """默认联系人类
    
    当无法获取联系人信息时使用的默认值
    """
    
    def __init__(self, wxid=""):
        self.wxid = wxid
        self.remark = wxid
        self.alias = wxid
        self.nickName = wxid
        self.smallHeadImgUrl = ""
        self.smallHeadImgBLOG = b''
        self.is_chatroom = False
        self.detail = {}

def get_contact(contact_info_list: list) -> Contact:
    """从信息列表创建联系人对象
    
    Args:
        contact_info_list: 包含联系人信息的列表
        
    Returns:
        Contact: 联系人对象
    """
    if not contact_info_list:
        return []
        
    detail = new_decode_extra_buf(contact_info_list[6])
    contact_info = {
        'UserName': contact_info_list[0],
        'Alias': contact_info_list[1],
        'Type': contact_info_list[2],
        'Remark': contact_info_list[3],
        'NickName': contact_info_list[4],
        'smallHeadImgUrl': contact_info_list[5],
        'detail': detail,
    }
    
    return Contact(contact_info)

@app.route('/msganalysis/<year>')
def msganalysis(year):
    """消息分析页面
    
    分析指定年份的聊天记录
    
    Args:
        year: 要分析的年份
        
    Returns:
        str: 渲染后的HTML页面
    """
    if not year:
        year = datetime.now().year
        
    wx = gmt.WeixinDbStorage()
    start = f"{year}-01-01"
    end = f"{year}-12-31"
    
    if re.match(r'^\d{4}-\d{2}-\d{2}$', start) and re.match(r'^\d{4}-\d{2}-\d{2}$', end):
        # 获取聊天排名前N的联系人
        contact_topN_num = wx.get_chatted_top_contacts(
            top_n=9999999,
            start=start, 
            end=end,
            contain_chatroom=True
        )

        total_msg_num = sum(num for _, num in contact_topN_num)
        
        # 获取联系人详细信息
        contact_topN = []
        contact_info_lists = wx.get_contact_by_usernames([wxid for wxid, _ in contact_topN_num])
        
        for wxid, num in contact_topN_num:
            contact = get_contact(contact_info_lists[contact_info_lists['username'] == wxid].values.tolist()[0])
            contact_topN.append([contact, num, 0])
            
        contacts_data = analysis.contacts_analysis(contact_topN)
        
        # 获取发送消息数量
        myusername = app.config['myusername'] if app.config['myusername'] else get_myusername()
        send_msg_num = wx.get_send_messages_number_sum(myusername, start=start, end=end)
        
        # 获取私聊联系人排名
        contact_topN = []
        contact_topN_num = wx.get_chatted_top_contacts(
            top_n=9999999,
            start=start,
            end=end,
            contain_chatroom=False
        )
        
        contact_info_lists = wx.get_contact_by_usernames([wxid for wxid, _ in contact_topN_num])
        
        for wxid, num in contact_topN_num[:6]:
            contact = get_contact(contact_info_lists[contact_info_lists['username'] == wxid].values.tolist()[0])
            text_length = wx.get_message_length(wxid, start=start, end=end)
            contact_topN.append([contact, num, text_length])

        # 获取消息统计数据
        my_message_counter_data = analysis.my_message_counter(
            start=start,
            end=end,
            my_name=myusername
        )
        
        # 整理数据用于模板渲染
        data = {
            'contact_topN': contact_topN,
            'contact_num': len(contact_topN_num),
            'send_msg_num': send_msg_num,
            'receive_msg_num': total_msg_num - send_msg_num,
        }
        
        return render_template('report.html',
                             **data,
                             **contacts_data,
                             **my_message_counter_data)
#region 聊天年度报告
@app.route("/christmas/<wxid>")
def christmas(wxid):
    """
    生成特定联系人的聊天报告
    Args:
        wxid: 联系人的微信ID 
    Returns:
        str: 渲染后的HTML页面
    """
    wx = gmt.WeixinDbStorage()
    
    # 获取时间范围
    start = request.args.get('start')
    end = request.args.get('end')
    
    if (start and end) and (re.match(r'^\d{4}-\d{2}-\d{2}$', start) and 
                           re.match(r'^\d{4}-\d{2}-\d{2}$', end)):
        pass
    else:
        start = ''
        end = ''
    
    # 获取联系人信息
    contact = get_contact(wx.get_contact_by_username(wxid))
    
    # 生成年份描述
    if start and end:
        year1 = start.split('-')[0]
        year2 = end.split('-')[0]
        year_s = f'{year1}年到{year2}年' if year1 != year2 else f'{year1}年'
    elif start:
        year1 = start.split('-')[0]
        year_s = f'{year1}年至今'
    elif end:
        year2 = end.split('-')[0]
        year_s = f'到{year2}年'
    else:
        year_s = '到现在'
    
    # 获取首次聊天时间
    try:
        first_time, first_message = wx.get_first_time_of_message(contact.wxid)
    except TypeError:
        first_time = '2023-01-01 00:00:00'
    
    # 获取消息统计数据
    msg_data = wx.get_messages_by_hour(contact.wxid, start=start, end=end)
    msg_data.sort(key=lambda x: x[1], reverse=True)
    
    # 定义时间段描述
    time_desc = {
        '夜猫子': {'22:00', '23:00', '00:00', '01:00', '02:00', '03:00', '04:00', '05:00'},
        '正常作息': {'06:00', "07:00", "08:00", "09:00", "10:00", "11:00", "12:00",
                     "13:00", "14:00", "15:00", "16:00", "17:00", "18:00", "19:00",
                     "20:00", "21:00"},
    }
    
    # 获取最活跃时间
    time_, num = msg_data[0] if msg_data else ('', 0)
    chat_time = f"凌晨{time_}" if f'{time_}:00' in {'00:00', '01:00', '02:00',
                                                    '03:00', '04:00', '05:00'} else time_
    
    # 确定作息类型
    label = '夜猫子'
    for key, times in time_desc.items():
        if f'{time_}:00' in times:
            label = key
    
    # 获取最近对话
    latest_dialog = wx.get_latest_time_of_message(contact.wxid, start=start, end=end)
    latest_time = latest_dialog[0][2] if latest_dialog else ''
    
    # 获取月度统计数据
    month_data = wx.get_messages_by_month(contact.wxid, start=start, end=end)
    
    if month_data:
        month_data.sort(key=lambda x: x[1])
        max_month, max_num = month_data[-1]
        min_month, min_num = month_data[0]
        min_month = min_month[-2:].lstrip('0') + '月'
        max_month = max_month[-2:].lstrip('0') + '月'
    else:
        max_month, max_num = '月份', 0
        min_month, min_num = '月份', 0
    
    # 获取表情包统计
    emoji_msgs = wx.get_msg_list_by_username(contact.wxid, start=start, end=end, type='47')
    
    # 获取用户头像
    df = wx.get_usernames_by_nicknames()
    myusername = app.config['myusername'] if app.config['myusername'] else get_myusername()
    my_headimg = df[df['username'] == myusername]['small_head_url'].values[0]
    
    top5_users = []
    if '@chatroom' in wxid:
        top5_users = wx.get_chatroom_msg_count(wxid,5, start, end)
        top5_users = [df[df['username'] == user[0]][['nickname','small_head_url']].values.tolist()[0] + [user[1]] for user in top5_users]

    # 整理模板数据
    template_data = {
        'ta_avatar_path': contact.smallHeadImgUrl,
        'ta_nickname': contact.remark,
        'my_nickname': '我',
        'first_time': first_time,
        'latest_time': latest_time,
        'latest_time_dialog': latest_dialog,
        'chat_time_label': label,
        'chat_time': chat_time,
        'chat_time_num': num,
        'year': '2023',
        'total_msg_num': wx.get_msg_count_by_username(contact.wxid, start=start, end=end),
        'max_month': max_month,
        'min_month': min_month,
        'max_month_num': max_num,
        'min_month_num': min_num,
        'emoji_total_num': len(emoji_msgs),
        'emoji_url': '',
        'emoji_num': 1,
        'top5_users': top5_users,
    }
    
    # 获取词云数据
    wordcloud_data = analysis.wordcloud_christmas(contact.wxid, start=start, end=end)
    
    # 获取日历图数据
    calendar_data = analysis.calendar_chart(contact.wxid, start=start, end=end)
    
    chart_room_data = analysis.chatroom_count(contact.wxid, top=5, start=start, end=end)

    return render_template("christmas.html",
                         **template_data,
                         **wordcloud_data,
                         **calendar_data,
                        #  **chart_room_data,
                         year_s=year_s,
                         my_avatar_path=my_headimg)

@app.route('/month_count', methods=['POST'])
def get_chart_options():
    """获取月度统计数据
    
    Returns:
        dict: 月度统计数据的JSON响应
    """
    wxid = request.json.get('wxid')
    time_range = request.json.get('time_range', [])
    start, end = time_range[0].split(' ')[0], time_range[1].split(' ')[0]
    
    data = analysis.month_count(wxid, start=start, end=end)
    return jsonify(data)

@app.route('/wordcloud', methods=['POST'])
def get_wordcloud():
    """获取词云数据
    
    Returns:
        dict: 词云数据的JSON响应
    """
    wxid = request.json.get('wxid')
    time_range = request.json.get('time_range', [])
    start, end = time_range[0].split(' ')[0], time_range[1].split(' ')[0]
    
    wordcloud_data = analysis.wordcloud_(wxid, start=start, end=end)
    return jsonify(wordcloud_data)

@app.route('/charts/<wxid>')
def charts(wxid):
    """图表展示页面
    
    Args:
        wxid: 联系人的微信ID
        
    Returns:
        str: 渲染后的HTML页面
    """
    wx = gmt.WeixinDbStorage()
    
    # 获取时间范围
    start = request.args.get('start')
    end = request.args.get('end')
    
    if (start and end) and (re.match(r'^\d{4}-\d{2}-\d{2}$', start) and 
                           re.match(r'^\d{4}-\d{2}-\d{2}$', end)):
        pass
    else:
        start = ''
        end = ''
    
    # 获取联系人信息
    contact = get_contact(wx.get_contact_by_username(wxid))
    
    try:
        # 获取首次和最后聊天时间
        first_time, _ = wx.get_first_time_of_message(contact.wxid)
        last_time, _ = wx.get_last_time_of_message2(contact.wxid)
    except TypeError:
        first_time = '2023-01-01 00:00:00'
        last_time = ''
    
    # 获取用户信息
    df = wx.get_usernames_by_nicknames()
    myusername = app.config['myusername'] if app.config['myusername'] else get_myusername()
    displayname, my_headimg = df[df['username']==myusername][['nickname','small_head_url']].values.tolist()[0]
    
    # 准备模板数据
    template_data = {
        'wxid': wxid,
        'my_nickname': displayname if displayname else myusername,
        'ta_nickname': contact.remark,
        'first_time': first_time,
        'last_time': last_time,
    }
    
    return render_template('charts.html',
                         **template_data,
                         start_time=start,
                         end_time=end,
                         my_avatar_path=my_headimg)

@app.route('/calendar', methods=['POST'])
def get_calendar():
    """获取日历图数据
    
    Returns:
        dict: 日历图数据的JSON响应
    """
    wxid = request.json.get('wxid')
    time_range = request.json.get('time_range', [])
    start, end = time_range[0].split(' ')[0], time_range[1].split(' ')[0]
    
    calendar_data = analysis.calendar_chart(wxid, start=start, end=end)
    return jsonify(calendar_data)

@app.route('/message_counter', methods=['POST'])
def get_counter():
    """获取消息统计数据
    
    Returns:
        dict: 消息统计数据的JSON响应
    """
    wx = gmt.WeixinDbStorage()
    wxid = request.json.get('wxid')
    time_range = request.json.get('time_range', [])
    start, end = time_range[0].split(' ')[0], time_range[1].split(' ')[0]
    
    contact = get_contact(wx.get_contact_by_username(wxid))
    myusername = app.config['myusername'] if app.config['myusername'] else get_myusername()
    
    data = analysis.sender(wxid,
                         start=start,
                         end=end,
                         my_name=myusername,
                         ta_name=contact.remark)
    return jsonify(data)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')