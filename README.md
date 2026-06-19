# 2233TicketBuy

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![Build](https://github.com/Oecxuan/2233TicketBuy/actions/workflows/build.yml/badge.svg)](https://github.com/Oecxuan/2233TicketBuy/actions)
[![Release](https://img.shields.io/github/v/release/Oecxuan/2233TicketBuy)](https://github.com/Oecxuan/2233TicketBuy/releases)

B站会员购抢票工具，仅供学习参考和研究使用。

本项目不开源任何账号信息，不上传任何数据。

> **免责声明：请遵守当地法律法规及B站相关规定，自行承担使用风险。严禁将本项目用于任何商业盈利行为。严禁进行任何形式的倒卖或违规行为。违反平台规则和法律所造成的一切后果由使用者自行承担，与本项目无关。**

## 感谢

- [biliTickerBuy](https://github.com/mikumifa/biliTickerBuy) 
- [BHYG](https://github.com/ZianTT/BHYG) 

## 功能

- 扫码登录
- 交互式选择项目
- 双服务器时间同步
- Windows 声音+弹窗（非阻塞）/ Linux 终端响铃 / QR 码

## 快速开始

```bash
pip install -r requirements.txt
python main.py
```

交互模式：登录 → 选活动 → 选票档 → 抢票。配置文件自动生成。

也可直接 `python main.py --grab`（需已配置完成）。

## 下载

前往 [Releases](https://github.com/Oecxuan/2233TicketBuy/releases) 下载对应平台版本：

- `2233TicketBuy_v*_Windows.exe`
- `2233TicketBuy_v*_Linux`

## 构建

```bash
pip install -r requirements.txt pyinstaller
python -m PyInstaller --clean 2233TicketBuy.spec
```

## 许可证

MIT License

## 联系

- [提交 Issue](../../issues)
- 如本项目存在侵犯 Bilibili 公司合法权益的内容，请提交 Issue 联系删除。

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=Oecxuan/2233TicketBuy&type=Date)](https://star-history.com/#Oecxuan/2233TicketBuy&Date)
