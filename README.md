# دستیار هوشمند معاملات ارز دیجیتال (Crypton)

سیستم تحلیل هوشمند بازار کریپتو با هوش مصنوعی داخلی — **ربات معامله‌گر نیست** و معامله واقعی انجام نمی‌دهد؛ هدف آن تحلیل بازار، یادگیری از نتایج قبلی و ارائه سیگنال‌های کوتاه‌مدت (تایم‌فریم ۵ دقیقه) با توضیح فارسی است.

## امکانات
- داشبورد فارسی RTL با طراحی دارک/بنفش و Glassmorphism، به‌روزرسانی زنده بدون رفرش (WebSocket)
- ۵ ارز پیش‌فرض: BTC، ETH، BNB، LINK، SOL (قابل افزودن از پنل ادمین)
- صفحه تحلیل هر ارز: چارت کندل‌استیک TradingView (۴ تایم‌فریم)، خطوط ورود/حد ضرر/حد سود، EMA
- لایه توضیح AI: چرایی سیگنال، عوامل مثبت/منفی، ریسک‌ها (به فارسی)
- ۵ استراتژی مستقل: روندگیری، شکست سطح، ورود در اصلاح، مومنتوم، محدوده
- موتور ساختار بازار: HH/HL/LH/LL، شکست ساختار (BOS)، تغییر کاراکتر (CHoCH)
- تحلیل مولتی‌تایم‌فریم: ۱h (روند اصلی)، 30m (قدرت روند)، 15m (ناحیه ورود)، 5m (تأیید ورود)
- موتور اعتماد ۰ تا ۱۰۰ (روند ۲۵ + مولتی‌تایم‌فریم ۲۵ + کیفیت ورود ۲۵ + مدیریت ریسک ۲۵)
- هوش مصنوعی داخلی (scikit-learn): آموزش اولیه با داده تاریخی + یادگیری مستمر از نتایج واقعی؛ **بدون هیچ API خارجی**
- Paper Trading: ثبت معامله شبیه‌سازی‌شده برای هر سیگنال و تغذیه حلقه یادگیری
- آمار دقت: کلی، به‌ازای هر ارز، هر استراتژی، و ۵۰ سیگنال اخیر
- نوتیفیکیشن درون‌برنامه‌ای + صدای هشدار برای سیگنال‌های مهم

## نصب و اجرا
```bash
pip install -r requirements.txt
cp .env.example .env          # در صورت نیاز پروکسی را تنظیم کنید
python manage.py migrate
python manage.py seed_coins
python manage.py train_ai     # بار اول: دانلود ~۴۵ روز داده و آموزش مدل (چند دقیقه)
python manage.py runserver    # worker به‌صورت خودکار داخل همین پروسه بالا می‌آید
```

سپس مرورگر را باز کنید: `http://127.0.0.1:8000/`

اجزای سیستم به‌صورت خودکار اجرا می‌شوند:
- به‌روزرسانی قیمت: هر ۱۰ ثانیه
- همگام‌سازی کندل‌ها: هر ۶۰ ثانیه
- تحلیل کامل و تولید سیگنال: هر ۵ دقیقه
- پایش حد سود/ضرر و منقضی‌سازی سیگنال‌ها: هر ۳۰ ثانیه

## نکات شبکه
اگر Binance از شبکه شما در دسترس نیست:
- در `.env` مقدار `BINANCE_PROXY` را تنظیم کنید (مثلاً `http://127.0.0.1:7890`)، یا
- `BINANCE_BASE_URL` را به یک میرور تغییر دهید، یا
- `DEMO_MODE=1` بگذارید تا با داده شبیه‌سازی‌شده کل سیستم قابل تست باشد.

## تنظیمات مهم (.env)
| کلید | پیش‌فرض | توضیح |
|---|---|---|
| `DEMO_MODE` | 0 | داده مصنوعی به‌جای API |
| `BINANCE_PROXY` | — | پروکسی HTTP برای دسترسی به Binance |
| `HISTORY_DAYS` | 45 | عمق داده تاریخی برای آموزش اولیه |
| `AI_RETRAIN_THRESHOLD` | 25 | تعداد نمونه جدید پیش از بازآموزی خودکار |
| `PAPER_TRADE_ENABLED` | 1 | فعال بودن معامله شبیه‌سازی‌شده |
| `WORKER_AUTOSTART` | 1 | اجرای خودکار worker در runserver |
| `DATABASE_ENGINE` | sqlite | برای PostgreSQL مقدار `django.db.backends.postgresql` + مقادیر اتصال |

## ساختار پروژه
```
config/           تنظیمات Django + ASGI (Channels)
apps/
  core/           worker پس‌زمینه + seed
  market_data/    کلاینت Binance + حالت دمو + مدل‌های Candle/Ticker
  analysis/       موتور تحلیل: اندیکاتورها، ساختار بازار، مولتی‌تایم‌فریم
  strategies/     ۵ استراتژی مستقل
  signals/        موتور اعتماد، Trade Setup، مدیریت سیگنال (بدون تکرار/انقضا)
  learning/       هوش مصنوعی داخلی: دیتاست، آموزش، یادگیری مستمر، آمار دقت
  paper_trading/  معامله شبیه‌سازی‌شده
  notifications/  نوتیفیکیشن درون‌برنامه‌ای
  dashboard/      UI فارسی RTL + REST API + WebSocket
```

## API (JSON)
- `GET /api/overview/` — قیمت و آخرین سیگنال همه ارزها
- `GET /api/coin/<BASE>/` — جزئیات کامل یک ارز + تاریخچه + عملکرد
- `GET /api/coin/<BASE>/candles/<tf>/` — کندل‌ها (tf: 5m/15m/30m/1h) + EMA + سطوح ورود/خروج
- `GET /api/performance/` — آمار دقت هوش مصنوعی
- `WS /ws/dashboard/` — به‌روزرسانی زنده

## نحوه اجرا (خلاصه)
```bash
git clone https://github.com/Aghalla/crypton-deploy.git
cd crypton-deploy
python -m venv .venv && source .venv/bin/activate  # ویندوز: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env   # SECRET_KEY و در صورت نیاز BINANCE_PROXY را پر کنید
python manage.py migrate
python manage.py seed_coins
python manage.py train_ai
python manage.py runserver
# http://127.0.0.1:8000
```

## اجرا با Docker (پیشنهادی برای همیشه روشن)
```bash
cp .env.example .env  # پر کنید
docker compose up -d          # یا: docker pull ghcr.io/aghalla/crypton-deploy:latest
# http://localhost:8000
# برای همیشه روشن باید روی سرور/VPS اجرا شود — روی PC شخصی با خاموش شدن سیستم، کانتینر هم خاموش می‌شود (restart: always فقط بعد از ریبوت سرور خودکار برمی‌گردد)
```

## لایسنس
MIT — فایل `LICENSE` را ببینید.

## یادداشت
این ابزار صرفاً تحلیلی و آموزشی است؛ خروجی آن توصیه مالی نیست.

> وایب کدش کردم — Vibe coded with AI ✨
