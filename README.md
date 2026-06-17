# 2233TicketBuy

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/)

B站会员购抢票工具，仅供技术学习和研究使用。

纯本地运行软件，不涉及任何账号信息上传。

> **免责声明：请遵守相关法律法规及B站服务条款，自行承担使用风险。请勿将本项目用于任何商业牟利行为，亦严禁用于任何形式的代抢、违法行为或违反相关平台规则的用途。由此产生的一切后果均由使用者自行承担，与本人无关。**

## 致谢

- [biliTickerBuy](https://github.com/mikumifa/biliTickerBuy) 
- [BHYG](https://github.com/ZianTT/BHYG)

## 快速开始

```bash
pip install -r requirements.txt
python main.py
```

交互模式：登录 → 选活动 → 选购票人 → 抢票。配置文件会自动生成。

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
- 如本项目中存在侵犯 Bilibili 公司合法权益的内容，需下线本项目，请联系我或者提交 Issue。
- 邮箱：41470775+Oecxuan@users.noreply.github.com

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=Oecxuan/2233TicketBuy&type=Date)](https://star-history.com/#Oecxuan/2233TicketBuy&Date)
