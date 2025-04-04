# Mechatmsg
# 微信聊天记录分析工具 (Mechatmsg)

- 一个用于分析和可视化微信聊天记录的Python工具。
- 根据大佬的开源项目修改而来，感谢大佬！原理可以参考：
- [WeChatMsg](https://github.com/LC044/WeChatMsg)，目前还未支持4.0版本微信
- [wechat-dump-rs](https://github.com/0xlane/wechat-dump-rs)，已经支持4.0版本微信


## 主要功能

- 微信聊天记录解密和导出
- 聊天记录数据分析和统计
- 聊天记录可视化展示
- 年度聊天报告生成
- ~~聊天记录导出（支持HTML、TXT、CSV格式）~~

## 项目结构

```
Mechatmsg/
├── bin/              # 可执行文件目录
├── data/             # 数据文件目录
├── db/               # 数据库文件目录
├── msg/              # 合并的数据库文件
├── resources/        # 资源文件目录
│   ├── data/        # 程序所需数据文件
│   └── icons/       # 图标资源文件
├── static/          # 静态资源文件
├── templates/       # HTML模板文件
├── analysis.py      # 数据分析模块
├── chuli.py         # 数据处理模块
├── getwxdata.py     # 微信数据获取模块
├── mainapp_new.py   # 主程序入口
└── region_conversion.py  # 地区转换模块
```

## 环境要求

- Python 3.7+
- 所需Python包在pyproject.toml中定义

## 主要功能模块

1. **数据获取模块**
   - 支持微信数据库文件读取
   - 聊天记录解密功能

2. **数据分析模块**
   - 聊天记录统计分析
   - 用户行为分析
   - 关键词提取

3. **可视化模块**
   - 聊天数据图表展示
   - 互动关系可视化
   - 年度报告生成

4. **数据导出模块**
   - 支持多种格式导出
   - 自定义导出模板

## 使用说明

1. 确保系统中已安装Python 3.7或更高版本
2. 安装所需依赖：
   ```
   pip install -r requirements.txt
   ```
3. 运行主程序：
   ```
   python mainapp.py
   ```
4. 使用
   ```
   uv run mainapp.py
   ```
   可以自动安装依赖并运行程序

5. 按照页面提示的ip地址和端口访问即可
   ```
   http://127.0.0.1:5000/
   ```

## 项目截图展示

### 1. 数据导入界面
![数据导入](static/img/解密页面.png)

## 注意事项

- 使用前请确保已备份微信数据
- 存在一定风险，使用需谨慎
- 请遵守相关法律法规，保护个人隐私

## 技术栈

- Python
- SQLite
- Flask
- 数据分析库（pandas, numpy等）
- 可视化库（echarts等）

## 许可证

本项目遵循GPL 3.0许可证。详情请参见LICENSE文件。
