# 2233TicketBuy

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/)

B站会员购抢票工具，仅供技术学习和研究使用。

纯本地运行软件，不涉及任何账号信息上传。

> **免责声明：请遵守相关法律法规及B站服务条款，自行承担使用风险。请勿用于商业用途。**

## 致谢

- [biliTickerBuy](https://github.com/mikumifa/biliTickerBuy) 
- [BHYG](https://github.com/ZianTT/BHYG)

## 快速开始

```bash
pip install -r requirements.txt
cp config.yaml.example config.yaml
python main.py
```

交互模式：登录 → 选活动 → 选购票人 → 抢票。

也可直接 `python main.py --grab`（需先完成过交互配置）。

## 打包

```bash
build.bat
# 或 python -m PyInstaller --clean 2233TicketBuy.spec
```

## 许可证

MIT License

## 联系

- [提交 Issue](../../issues)
- 如需下线本项目，请联系我或者提交 Issue。
- 邮箱：41470775+Oecxuan@users.noreply.github.com
