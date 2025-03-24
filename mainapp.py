from datetime import datetime
import re
from flask import Flask, jsonify, render_template, request, redirect, url_for
import getwxdata as gmt
import pandas as pd
import numpy as np
from chuli import get_current_progress, main, find
import subprocess
import os
import shutil

if not os.path.exists("./db"):
    os.mkdir("./db")

import analysis
# import analysis_new as analysis

app = Flask(__name__)

_progress = 0

def get_myusername():
    wx = gmt.WeixinDbStorage()
    myusername = wx.get_all_usernames_matching_encrypt()
    return myusername[0] if myusername and myusername[0]!='' else None

@app.route('/')
def index():
    try:
        app.config['myusername'] = get_myusername()
        wx = gmt.WeixinDbStorage()
        df = wx.get_usernames_by_nicknames()
        if df.empty:
            return redirect(url_for('decrypt'))
        return render_template('index2.html', contacts= zip(df['nickname'], df['username'],df['small_head_url'], df['remark']), myname=app.config['myusername'] if app.config['myusername'] else get_myusername())
    except:
        return redirect(url_for('decrypt'))

@app.route('/get_progress')
def get_progress():
    if _progress == 0:
        return jsonify({'progress': 0})
    return jsonify({'progress': get_current_progress()})

@app.route('/check_decrypted_data')
def check_decrypted_data():
    # 检查merged.db是否存在
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
    global _progress
    try:
        dblist = os.listdir("./db")
        p = subprocess.Popen(["./bin/wechat-dump-rs.exe", "-a" ,"-o", ".\db"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = p.communicate()
        if err:
            if "WeChat is not running" in err.decode("utf-8"):
                return jsonify({'success': False, 'error': "微信未运行"})
            return jsonify({'success': False, 'error': err.decode("utf-8")})
        print(out.decode("utf-8"))
        print(os.listdir("./db"))
        # print("解密完成", out.decode("utf-8"))
        for db in dblist: 
            folder_path = f"./db/{db}"
            print("删除文件夹", folder_path)
            shutil.rmtree(folder_path)
        if os.path.exists('msg/merged.db'):
            os.remove("msg/merged.db")
        
        # 启动解密过程
        contact_db_fp = find(".", "contact.db")
        if contact_db_fp and find(".", "message_?.db"):
            _progress = 1
            chuli = main()
            if chuli:
                return jsonify({'success': True})
            return jsonify({'success': False, 'error': "解密失败2"})
        
        return start_decrypt()
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

#数据解密路由
@app.route('/decrypt', methods=['GET', 'POST'])
def decrypt():
    if request.method == 'GET':
        return render_template('decrypt.html')
    elif request.method == 'POST':
        # 启动解密过程
        chuli = main()
        return redirect(url_for('index'))

@app.route('/get_message', methods=['POST'])
def get_message():
    username = request.json["username"]
    page = request.json.get("page", 1)  # 默认第一页
    per_page = request.json.get("per_page", 100)  # 默认每页50条
    print(username, page, per_page)
    wx = gmt.WeixinDbStorage()
    
    try:
        # 获取总消息数量（优化查询）
        total_msg = wx.get_msg_count_by_username(username)
        print('总消息数量', total_msg)
        if total_msg/per_page + 1 <= page:
            return jsonify([])
        # 分页查询消息
        msg_list = wx.get_msg_list_by_username_paged(username, '', '', page, per_page)
        # print('msg_list', msg_list[:10])
        # 数据处理逻辑（保持原有逻辑）
        msg_content_list = [[item[1],item[-1].decode(errors='ignore'), item[-2]] for item in msg_list]

        df = wx.get_contact_by_usernames(list(set([item[0] for item in msg_content_list])))

        df['显示名'] = np.where(df['remark']!='', df['remark'], df['nickname'])
        # print(msg_content_list[:10])
        datas = [[username, msg, df[df['username'] == username]['显示名'].values[0], t] for username, msg, t in msg_content_list]

        # print('记录', datas[3:7])
        
        return jsonify({
            "data": datas,
            "total": total_msg,
            "page": page,
            "per_page": per_page
        })
    except Exception as e:
        print(e)
        return jsonify([])

def decodeExtraBuf(extra_buf_content: bytes):
    if not extra_buf_content:
        return {
            "region": ('', '', ''),
            "signature": '',
            "telephone": '',
            "gender": 0,
        }
    trunkName = {
        b"\x46\xCF\x10\xC4": "个性签名",
        b"\xA4\xD9\x02\x4A": "国家",
        b"\xE2\xEA\xA8\xD1": "省份",
        b"\x1D\x02\x5B\xBF": "市",
        # b"\x81\xAE\x19\xB4": "朋友圈背景url",
        # b"\xF9\x17\xBC\xC0": "公司名称",
        # b"\x4E\xB9\x6D\x85": "企业微信属性",
        # b"\x0E\x71\x9F\x13": "备注图片",
        b"\x75\x93\x78\xAD": "手机号",
        b"\x74\x75\x2C\x06": "性别",
    }
    res = {"手机号": ""}
    off = 0
    try:
        for key in trunkName:
            trunk_head = trunkName[key]
            try:
                off = extra_buf_content.index(key) + 4
            except:
                pass
            char = extra_buf_content[off: off + 1]
            off += 1
            if char == b"\x04":  # 四个字节的int，小端序
                intContent = extra_buf_content[off: off + 4]
                off += 4
                intContent = int.from_bytes(intContent, "little")
                res[trunk_head] = intContent
            elif char == b"\x18":  # utf-16字符串
                lengthContent = extra_buf_content[off: off + 4]
                off += 4
                lengthContent = int.from_bytes(lengthContent, "little")
                strContent = extra_buf_content[off: off + lengthContent]
                off += lengthContent
                res[trunk_head] = strContent.decode("utf-16").rstrip("\x00")
        return {
            "region": (res["国家"], res["省份"], res["市"]),
            "signature": res["个性签名"],
            "telephone": res["手机号"],
            "gender": res["性别"],
        }
    except:
        # logger.error(f'联系人解析错误:\n{traceback.format_exc()}')
        return {
            "region": ('', '', ''),
            "signature": '',
            "telephone": '',
            "gender": 0,
        }

def newdecodeExtraBuf(extra_buf_content: bytes):
    if not extra_buf_content:
        return {
            "region": ('', '', ''),
            "signature": '',
            "telephone": '',
            "gender": 0,
        }
    res = {"手机号": "","性别":extra_buf_content[1]}
    aa = []
    s = [b'\x18\x00\x22',b'\x2a',b'2',b':',b'@']
    for i in range(len(s)-1):
        try:
            aa.append([extra_buf_content.index(s[i]) + len(s[i]) + 1,extra_buf_content.index(s[i+1])])
        except:
            aa.append([0,0])
    
    trunkName = ["个性签名","国家","省份","市"]
    for i, p in enumerate(aa):
        try:
            res[trunkName[i]] = extra_buf_content[p[0]:p[-1]].decode(errors='ignore')
        except:
            pass
    
    return {
            "region": (res["国家"], res["省份"], res["市"]),
            "signature": res["个性签名"],
            "telephone": res["手机号"],
            "gender": res["性别"],
        }

class Contact():
    def __init__(self, contact_info: dict):
        super().__init__()
        self.wxid = contact_info.get('UserName')
        self.remark = contact_info.get('Remark')
        # Alias,Type,Remark,NickName,PYInitial,RemarkPYInitial,ContactHeadImgUrl.smallHeadImgUrl,ContactHeadImgUrl,bigHeadImgUrl
        self.alias = contact_info.get('Alias')
        self.nickName = contact_info.get('NickName')
        if not self.remark:
            self.remark = self.nickName
        self.remark = re.sub(r'[\\/:*?"<>|\s\.]', '_', self.remark)
        self.smallHeadImgUrl = contact_info.get('smallHeadImgUrl')
        self.smallHeadImgBLOG = b''
        self.is_chatroom = self.wxid.__contains__('@chatroom')
        self.detail: dict = contact_info.get('detail')
        # self.label_name = contact_info.get('label_name')  # 联系人的标签分类

        """
        detail存储了联系人的详细信息，是个字典
        {
            'region': tuple[国家,省份,市], # 地区三元组
            'signature': str, # 个性签名
            'telephone': str, # 电话号码，自己写的备注才会显示
            'gender': int, # 性别 0：未知，1：男，2：女
        }
        """

class ContactDefault():
    def __init__(self, wxid=""):
        super().__init__()
        self.wxid = wxid
        self.remark = wxid
        self.alias = wxid
        self.nickName = wxid
        self.smallHeadImgUrl = ""
        self.smallHeadImgBLOG = b''
        self.is_chatroom = False
        self.detail = {}

def get_contact(contact_info_list: list) -> Contact:
    if not contact_info_list:
        return []
    detail = newdecodeExtraBuf(contact_info_list[6])
    # detail = {}
    contact_info = {
        'UserName': contact_info_list[0],
        'Alias': contact_info_list[1],
        'Type': contact_info_list[2],
        'Remark': contact_info_list[3],
        'NickName': contact_info_list[4],
        'smallHeadImgUrl': contact_info_list[5],
        # 'label_name': contact_info_list[10],
        'detail': detail,
    }
    contact =Contact(contact_info)
    # print(detail)

    return contact

@app.route('/msganalysis/<year>')
def msganalysis(year):
    if not year:
        year = datetime.datetime.now().year
    wx = gmt.WeixinDbStorage()
    start = f"{year}-01-01"
    end = f"{year}-12-31"
    if re.match(r'^\d{4}-\d{2}-\d{2}$', start) and re.match(r'^\d{4}-\d{2}-\d{2}$', end):
        print(start, end)
        contact_topN_num = wx.get_chatted_top_contacts(top_n=9999999,start=start, end=end, contain_chatroom=True)

        total_msg_num = sum(list(map(lambda x: x[1], contact_topN_num)))
        contact_topN = []
        contact_info_lists = wx.get_contact_by_usernames([wxid for wxid, num in contact_topN_num])
        for wxid, num in contact_topN_num:
            contact = get_contact(contact_info_lists[contact_info_lists['username'] == wxid].values.tolist()[0])
            text_length = 0
            contact_topN.append([contact, num, text_length])
        # print(contact_topN)
        contacts_data = analysis.contacts_analysis(contact_topN)
        
        contact_topN = []
        send_msg_num = wx.get_send_messages_number_sum(app.config['myusername'] if app.config['myusername'] else get_myusername(), start=start, end=end)
        
        contact_topN_num = wx.get_chatted_top_contacts(top_n=9999999,start=start, end=end, contain_chatroom=False)
        
        contact_info_lists = wx.get_contact_by_usernames([wxid for wxid, num in contact_topN_num])
        for wxid, num in contact_topN_num[:6]:
            contact = get_contact(contact_info_lists[contact_info_lists['username'] == wxid].values.tolist()[0])
            text_length = wx.get_message_length(wxid, start=start, end=end)
            contact_topN.append([contact, num, text_length])

        my_message_counter_data = analysis.my_message_counter(start=start, end=end, my_name=app.config['myusername'] if app.config['myusername'] else get_myusername())
        data = {
            # 'avatar': Me().smallHeadImgUrl,
            'contact_topN': contact_topN,
            'contact_num': len(contact_topN_num),
            'send_msg_num': send_msg_num,
            'receive_msg_num': total_msg_num - send_msg_num,
        }
        return render_template('report.html', **data,**contacts_data, **my_message_counter_data)


@app.route("/christmas/<wxid>")
def christmas(wxid):
    wx = gmt.WeixinDbStorage()
    start =  request.args.get('start')
    end =  request.args.get('end')
    print('start',start)
    if (start != None and end != None) and (re.match(r'^\d{4}-\d{2}-\d{2}$', start) and re.match(r'^\d{4}-\d{2}-\d{2}$', end)):
        pass
    else:
        start = ''
        end = ''
    
    contact = get_contact(wx.get_contact_by_username(wxid))
    # 渲染模板，并传递图表的 HTML 到模板中
    if start and end:
        year1 = start.split('-')[0]
        year2 = end.split('-')[0]
        year_s = f'{year1}年到{year2}年'
        if year1 == year2:
            year_s = f'{year1}年'
    elif start:
        year1 = start.split('-')[0]
        year_s = f'{year1}年至今'
    elif end:
        year2 = end.split('-')[0]
        year_s = f'到{year2}年'
    else:
        year_s = '到现在'
    
    try:
        first_time, first_message = wx.get_first_time_of_message(contact.wxid)
    except TypeError:
        first_time = '2023-01-01 00:00:00'
    data = {
        'ta_avatar_path': contact.smallHeadImgUrl,
        # 'my_avatar_path': Me().smallHeadImgUrl,
        'ta_nickname': contact.remark,
        'my_nickname': '我',
        'first_time': first_time,
    }
    wordcloud_cloud_data = analysis.wordcloud_christmas(contact.wxid,start=start, end=end)
    msg_data = wx.get_messages_by_hour(contact.wxid,start=start, end=end)
    msg_data.sort(key=lambda x: x[1], reverse=True)
    desc = {
        '夜猫子': {'22:00', '23:00', '00:00', '01:00', '02:00', '03:00', '04:00', '05:00'},
        '正常作息': {'06:00', "07:00", "08:00", "09:00", "10:00", "11:00", "12:00", "13:00", "14:00", "15:00", "16:00",
                     "17:00", "18:00", "19:00", "20:00", "21:00"},
    }
    time_, num = msg_data[0] if msg_data else ('', 0)
    print(time_)
    chat_time = f"凌晨{time_}" if f'{time_}:00' in {'00:00', '01:00', '02:00', '03:00', '04:00', '05:00'} else time_
    label = '夜猫子'
    for key, item in desc.items():
        if f'{time_}:00' in item:
            label = key
    
    print(contact.wxid)
    latest_dialog = wx.get_latest_time_of_message(contact.wxid,start=start, end=end)
    latest_time = latest_dialog[0][2] if latest_dialog else ''
    time_data = {
        'latest_time': latest_time,
        'latest_time_dialog': latest_dialog,
        'chat_time_label': label,
        'chat_time': chat_time,
        'chat_time_num': num,
    }
    month_data = wx.get_messages_by_month(contact.wxid,start=start, end=end)

    if month_data:
        month_data.sort(key=lambda x: x[1])
        max_month, max_num = month_data[-1]
        min_month, min_num = month_data[0]
        min_month = min_month[-2:].lstrip('0') + '月'
        max_month = max_month[-2:].lstrip('0') + '月'
    else:
        max_month, max_num = '月份', 0
        min_month, min_num = '月份', 0

    month_data = {
        'year': '2023',
        'total_msg_num': wx.get_msg_count_by_username(contact.wxid,start=start, end=end),
        'max_month': max_month,
        'min_month': min_month,
        'max_month_num': max_num,
        'min_month_num': min_num,
    }

    calendar_data = analysis.calendar_chart(contact.wxid, start=start, end=end)
    emoji_msgs = wx.get_msg_list_by_username(contact.wxid,start=start, end=end, type='47')
    url, num = '',1
    emoji_data = {
        'emoji_total_num': len(emoji_msgs),
        'emoji_url': url,
        'emoji_num': num,
    }
    global html
    df = wx.get_usernames_by_nicknames()
    my_headimg = df[df['username'] == app.config['myusername'] if app.config['myusername'] else get_myusername()]['small_head_url'].values[0]
    html = render_template("christmas.html", **data, **wordcloud_cloud_data, **time_data, **month_data, **calendar_data, **emoji_data, year_s=year_s, my_avatar_path = my_headimg)
    return html

@app.route('/month_count', methods=['POST'])
def get_chart_options():
    wxid = request.json.get('wxid')
    time_range = request.json.get('time_range', [])
    start,end = time_range[0].split(' ')[0], time_range[1].split(' ')[0]
    data = analysis.month_count(wxid,  start=start, end=end)
    return jsonify(data)

@app.route('/wordcloud', methods=['POST'])
def get_wordcloud():
    wxid = request.json.get('wxid')
    time_range = request.json.get('time_range', [])
    start,end = time_range[0].split(' ')[0], time_range[1].split(' ')[0]
    world_cloud_data = analysis.wordcloud_(wxid, start=start, end=end)
    return jsonify(world_cloud_data)

@app.route('/charts/<wxid>')
def charts(wxid):
    # 渲染模板，并传递图表的 HTML 到模板中
    wx = gmt.WeixinDbStorage()
    start =  request.args.get('start')
    end =  request.args.get('end')
    print('start',start)
    if (start != None and end != None) and (re.match(r'^\d{4}-\d{2}-\d{2}$', start) and re.match(r'^\d{4}-\d{2}-\d{2}$', end)):
        pass
    else:
        start = ''
        end = ''
    contact = get_contact(wx.get_contact_by_username(wxid))
    # 渲染模板，并传递图表的 HTML 到模板中
    try:
        first_time, first_message = wx.get_first_time_of_message(contact.wxid)
        last_time, last_message  = wx.get_last_time_of_message2(contact.wxid)
        
    except TypeError:
        first_time = '2023-01-01 00:00:00'
    df = wx.get_usernames_by_nicknames()
    displayname, my_headimg= df[df['username']==app.config['myusername'] if app.config['myusername'] else get_myusername()][['nickname','small_head_url']].values.tolist()[0]

    print('my_headimg',my_headimg)
    data = {
        'wxid': wxid,
        'my_nickname': displayname if displayname else app.config['myusername'] if app.config['myusername'] else get_myusername(),
        'ta_nickname': contact.remark,
        'first_time': first_time,
        'last_time': last_time,
    }
    return render_template('charts.html', **data, start_time=start, end_time = end, my_avatar_path = my_headimg)

@app.route('/calendar', methods=['POST'])
def get_calendar():
    wxid = request.json.get('wxid')
    time_range = request.json.get('time_range', [])
    start,end = time_range[0].split(' ')[0], time_range[1].split(' ')[0]
    world_cloud_data = analysis.calendar_chart(wxid, start=start, end=end)
    return jsonify(world_cloud_data)


@app.route('/message_counter', methods=['POST'])
def get_counter():
    wx = gmt.WeixinDbStorage()
    wxid = request.json.get('wxid')
    time_range = request.json.get('time_range', [])
    start,end = time_range[0].split(' ')[0], time_range[1].split(' ')[0]

    contact = get_contact(wx.get_contact_by_username(wxid))
    data = analysis.sender(wxid, start=start, end=end, my_name=app.config['myusername'] if app.config['myusername'] else get_myusername(), ta_name=contact.remark)
    return jsonify(data)

if __name__ == '__main__':
    # myname = get_myusername()
    app.run(debug=True, host='0.0.0.0')