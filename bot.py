# -*- coding: utf-8 -*-
"""
OVOZ BATL bot - kanallarda ovozli konkurslar (battle) o'tkazish uchun Telegram bot.
Kutubxona: pyTelegramBotAPI   ->   pip3 install --user pyTelegramBotAPI
Token: token.txt faylida (yoki BOT_TOKEN muhit o'zgaruvchisida).
"""
import os, re, json, time, sqlite3, threading, html, logging
from datetime import datetime

import telebot
from telebot import types

BASE = os.path.dirname(os.path.abspath(__file__))
logging.basicConfig(level=logging.INFO)
telebot.logger.setLevel(logging.INFO)


def load_token():
    t = os.environ.get("BOT_TOKEN")
    if t:
        return t.strip()
    with open(os.path.join(BASE, "token.txt"), encoding="utf-8") as f:
        return f.read().strip()


TOKEN = load_token()
ADMIN_ID = int(os.environ.get("ADMIN_ID", "8611446922"))  # murojaatlar shu odamga boradi
TZ_OFFSET = 5 * 3600  # O'zbekiston vaqti (UTC+5)

bot = telebot.TeleBot(TOKEN, parse_mode="HTML", threaded=True)

# ----------------------------------------------------------------- DB
db = sqlite3.connect(os.path.join(BASE, "batl.db"), check_same_thread=False)
db.row_factory = sqlite3.Row
lock = threading.RLock()

with lock:
    db.executescript("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY, name TEXT, username TEXT,
        lang TEXT DEFAULT 'uz', joined INTEGER);
    CREATE TABLE IF NOT EXISTS battles(
        id INTEGER PRIMARY KEY AUTOINCREMENT, owner INTEGER, title TEXT,
        options TEXT, hours INTEGER, status TEXT DEFAULT 'pending',
        channel_id INTEGER, channel_username TEXT, message_id INTEGER,
        end_ts INTEGER, created INTEGER);
    CREATE TABLE IF NOT EXISTS votes(
        battle_id INTEGER, user_id INTEGER, opt INTEGER, ts INTEGER,
        PRIMARY KEY(battle_id, user_id));
    """)
    db.commit()


def run(sql, args=()):
    with lock:
        cur = db.execute(sql, args)
        db.commit()
        return cur.lastrowid


def get(sql, args=()):
    with lock:
        return db.execute(sql, args).fetchall()


def one(sql, args=()):
    with lock:
        return db.execute(sql, args).fetchone()


# ----------------------------------------------------------------- texts
T = {
    "uz": {
        "btn_create": "🏆 Battle yaratish",
        "btn_my": "📅 Mening battlelarim",
        "btn_check": "📊 Battle Tekshirish",
        "btn_help": "📰 Qo'llanma",
        "btn_profile": "👤 Profil",
        "btn_lang": "🌐 Til",
        "btn_contact": "✉️ Murojaat",
        "welcome": (
            "🎉 <b>Botimizga xush kelibsiz!</b>\n\n"
            "📌 <b>Ushbu Bot Orqali Siz:</b>\n\n"
            "📣 Kanallaringizda Ovozli Konkurslar Qilishingiz Mumkin!\n\n"
            "🎖 Botni Kanalga Admin Qiling\n"
            "🥇 Kanalga #batl deb yozib yuboring tayyor ⭐\n\n"
            "📌 <b>Foydali Taraflar</b>\n\n"
            "👥 Ovoz Beruvchilar Kanalingizga Obuna Bo'lishadi ⭐\n\n"
            "❗ Agar Ovoz beruvchi kanaldan chiqib ketsa, ovozi avtomatik real vaqtda ayriladi ⭐\n\n"
            "⬇️ Quyidagi menyudan birini tanlang:"),
        "menu": "Bosh menyu",
        "ask_title": "🏆 <b>Battle yaratish</b>\n\n📝 Battle nomini kiriting\n\nMisol:\n• Yozgi batl 🔥\n\n❌ Bekor qilish: /cancel",
        "ask_count": "👥 Nechta ishtirokchi bo'ladi? 2 dan 6 gacha raqam yuboring.",
        "ask_opt": "✍️ {i}-ishtirokchi nomini kiriting (jami {n} ta):",
        "ask_hours": "⏳ Battle necha soat davom etadi? 1 dan 720 gacha raqam yuboring.",
        "created": (
            "✅ <b>Battle tayyor!</b>\n\n"
            "1️⃣ Botni kanalingizga <b>admin</b> qiling (xabar yozish va o'chirish huquqi bilan).\n"
            "2️⃣ Kanalga <b>#batl</b> deb yozib yuboring.\n\n"
            "Battle shu yerda e'lon qilinadi va vaqt shu paytdan boshlab hisoblanadi."),
        "published": "🚀 «{title}» battle kanalda e'lon qilindi!",
        "ended_owner": "🏁 «{title}» battle tugadi!",
        "bad_number": "⚠️ To'g'ri raqam kiriting.",
        "bad_text": "⚠️ Matn yuboring (40 belgigacha).",
        "no_battles": "📅 Sizda hozircha battle yo'q.",
        "my_title": "📅 <b>Mening battlelarim</b>",
        "st_pending": "⏳ kutilmoqda",
        "st_active": "🟢 faol",
        "st_ended": "🏁 tugagan",
        "not_sub": "❗ Ovoz berish uchun avval kanalga obuna bo'ling!",
        "voted": "✅ Ovozingiz qabul qilindi!",
        "already": "Siz allaqachon ovoz bergansiz.",
        "closed": "🏁 Bu battle tugagan.",
        "check_ask": "📊 <b>BATTLE TEKSHIRISH</b>\n\n📣 Kanaldagi ovoz batl xabarini forward qilib yuboring.\n\n❗ <i>Faqat kanal postlarini forward qiling!</i>\n\n❌ Bekor qilish: /cancel",
        "check_none": "🔎 Bunday battle topilmadi. Kanaldagi battle xabarini forward qiling.",
        "no_admin_battle": "Sizda hozircha hech qanday kanal admini sifatida yaratilgan battle topilmadi.\n\nBotni kanalingizga admin qiling va #batl deb yozing — battle shu yerda ko'rinadi.",
        "profile": (
            "👤 <b>Mening profilim</b>\n\n"
            "🆔 ID: <code>{id}</code>\n📛 Ism: {name}\n🔗 Username: {username}\n"
            "🌐 Til: {lang}\n📆 Ro'yxatdan o'tgan: {joined}\n\n"
            "🏆 Yaratgan battlelar: <b>{created}</b>\n🎯 Qatnashgan battlelar: <b>{joined_b}</b>\n"
            "🗳 Bergan ovozlar: <b>{given}</b>\n📥 Olgan ovozlar: <b>{got}</b>"),
        "help": (
            "🎉 <b>Botimizga xush kelibsiz!</b>\n\n"
            "📌 <b>Ushbu Bot Orqali Siz:</b>\n"
            "📣 Kanallaringizda Ovozli Konkurslar Qilishingiz Mumkin!\n"
            "🎖 Botni Kanalga Admin Qiling\n"
            "🥇 Kanalga #batl deb yozib yuboring tayyor ✅\n\n"
            "📌 <b>Foydali Taraflar</b>\n"
            "👥 Ovoz Beruvchilar Kanalingizga Obuna Bo'lishadi ✅\n"
            "❗ Agar Ovoz beruvchi kanaldan chiqib ketsa, ovozi avtomatik real vaqtda ayriladi ✅"),
        "choose_lang": "🌐 Tilni tanlang / Choose language / Выберите язык:",
        "lang_set": "✅ Til o'zgartirildi.",
        "contact_ask": "✉️ Xabaringizni yozing, admin javob beradi.\n\n❌ Bekor qilish: /cancel",
        "contact_sent": "✅ Xabaringiz adminga yuborildi.",
        "finish": "⏹ Tugatish",
        "delete": "🗑 O'chirish",
        "back": "⬅️ Orqaga",
        "ends": "Tugash",
        "total": "Jami ovozlar",
        "winner": "🥇 G'olib",
        "draw": "🤝 G'olib aniqlanmadi",
        "over": "🏁 Battle tugadi",
        "votes": "ovoz",
        "wait_pub": "kanalda #batl yozing",
        "done": "✅ Bajarildi.",
        "langname": "O'zbekcha",
    },
    "en": {
        "btn_create": "🏆 Create battle",
        "btn_my": "📅 My battles",
        "btn_check": "📊 Check battle",
        "btn_help": "📰 Guide",
        "btn_profile": "👤 Profile",
        "btn_lang": "🌐 Language",
        "btn_contact": "✉️ Contact",
        "welcome": (
            "🎉 <b>Welcome to our bot!</b>\n\n"
            "📌 <b>With this bot you can:</b>\n\n"
            "📣 Run voting contests in your channels!\n\n"
            "🎖 Make the bot an admin of your channel\n"
            "🥇 Post #batl in the channel and you're done ⭐\n\n"
            "📌 <b>Benefits</b>\n\n"
            "👥 Voters subscribe to your channel ⭐\n\n"
            "❗ If a voter leaves the channel, their vote is removed automatically in real time ⭐\n\n"
            "⬇️ Choose an option from the menu below:"),
        "menu": "Main menu",
        "ask_title": "🏆 <b>Create battle</b>\n\n📝 Enter the battle name\n\nExample:\n• Summer battle 🔥\n\n❌ Cancel: /cancel",
        "ask_count": "👥 How many participants? Send a number from 2 to 6.",
        "ask_opt": "✍️ Enter the name of participant {i} (of {n}):",
        "ask_hours": "⏳ How many hours will the battle last? Send a number from 1 to 720.",
        "created": (
            "✅ <b>Battle is ready!</b>\n\n"
            "1️⃣ Make the bot an <b>admin</b> of your channel (with permission to post and delete messages).\n"
            "2️⃣ Post <b>#batl</b> in the channel.\n\n"
            "The battle will be published there and the timer starts at that moment."),
        "published": "🚀 Battle «{title}» was published in the channel!",
        "ended_owner": "🏁 Battle «{title}» has finished!",
        "bad_number": "⚠️ Enter a valid number.",
        "bad_text": "⚠️ Send text (up to 40 characters).",
        "no_battles": "📅 You have no battles yet.",
        "my_title": "📅 <b>My battles</b>",
        "st_pending": "⏳ pending",
        "st_active": "🟢 active",
        "st_ended": "🏁 finished",
        "not_sub": "❗ Subscribe to the channel first to vote!",
        "voted": "✅ Your vote has been counted!",
        "already": "You have already voted.",
        "closed": "🏁 This battle has finished.",
        "check_ask": "📊 <b>CHECK BATTLE</b>\n\n📣 Forward the battle post from the channel.\n\n❗ <i>Forward channel posts only!</i>\n\n❌ Cancel: /cancel",
        "check_none": "🔎 Battle not found. Forward the battle post from the channel.",
        "no_admin_battle": "No battles created as a channel admin were found.\n\nMake the bot an admin of your channel and post #batl — the battle will show up here.",
        "profile": (
            "👤 <b>My profile</b>\n\n"
            "🆔 ID: <code>{id}</code>\n📛 Name: {name}\n🔗 Username: {username}\n"
            "🌐 Language: {lang}\n📆 Registered: {joined}\n\n"
            "🏆 Battles created: <b>{created}</b>\n🎯 Battles joined: <b>{joined_b}</b>\n"
            "🗳 Votes given: <b>{given}</b>\n📥 Votes received: <b>{got}</b>"),
        "help": (
            "🎉 <b>Welcome to our bot!</b>\n\n"
            "📌 <b>With this bot you can:</b>\n"
            "📣 Run voting contests in your channels!\n"
            "🎖 Make the bot an admin of your channel\n"
            "🥇 Post #batl in the channel and you're done ✅\n\n"
            "📌 <b>Benefits</b>\n"
            "👥 Voters subscribe to your channel ✅\n"
            "❗ If a voter leaves the channel, their vote is removed automatically in real time ✅"),
        "choose_lang": "🌐 Tilni tanlang / Choose language / Выберите язык:",
        "lang_set": "✅ Language changed.",
        "contact_ask": "✉️ Write your message, the admin will reply.\n\n❌ Cancel: /cancel",
        "contact_sent": "✅ Your message was sent to the admin.",
        "finish": "⏹ Finish",
        "delete": "🗑 Delete",
        "back": "⬅️ Back",
        "ends": "Ends",
        "total": "Total votes",
        "winner": "🥇 Winner",
        "draw": "🤝 No winner",
        "over": "🏁 Battle finished",
        "votes": "votes",
        "wait_pub": "post #batl in the channel",
        "done": "✅ Done.",
        "langname": "English",
    },
    "ru": {
        "btn_create": "🏆 Создать батл",
        "btn_my": "📅 Мои батлы",
        "btn_check": "📊 Проверить батл",
        "btn_help": "📰 Инструкция",
        "btn_profile": "👤 Профиль",
        "btn_lang": "🌐 Язык",
        "btn_contact": "✉️ Обращение",
        "welcome": (
            "🎉 <b>Добро пожаловать в наш бот!</b>\n\n"
            "📌 <b>С помощью этого бота вы можете:</b>\n\n"
            "📣 Проводить голосовые конкурсы в своих каналах!\n\n"
            "🎖 Сделайте бота админом канала\n"
            "🥇 Напишите в канале #batl и всё готово ⭐\n\n"
            "📌 <b>Преимущества</b>\n\n"
            "👥 Голосующие подписываются на ваш канал ⭐\n\n"
            "❗ Если голосующий выйдет из канала, его голос автоматически снимается в реальном времени ⭐\n\n"
            "⬇️ Выберите пункт меню ниже:"),
        "menu": "Главное меню",
        "ask_title": "🏆 <b>Создать батл</b>\n\n📝 Введите название батла\n\nПример:\n• Летний батл 🔥\n\n❌ Отмена: /cancel",
        "ask_count": "👥 Сколько будет участников? Отправьте число от 2 до 6.",
        "ask_opt": "✍️ Введите имя участника {i} (всего {n}):",
        "ask_hours": "⏳ Сколько часов продлится батл? Отправьте число от 1 до 720.",
        "created": (
            "✅ <b>Батл готов!</b>\n\n"
            "1️⃣ Сделайте бота <b>админом</b> канала (с правом писать и удалять сообщения).\n"
            "2️⃣ Напишите в канале <b>#batl</b>.\n\n"
            "Батл будет опубликован там, и время начнётся с этого момента."),
        "published": "🚀 Батл «{title}» опубликован в канале!",
        "ended_owner": "🏁 Батл «{title}» завершён!",
        "bad_number": "⚠️ Введите корректное число.",
        "bad_text": "⚠️ Отправьте текст (до 40 символов).",
        "no_battles": "📅 У вас пока нет батлов.",
        "my_title": "📅 <b>Мои батлы</b>",
        "st_pending": "⏳ ожидает",
        "st_active": "🟢 активен",
        "st_ended": "🏁 завершён",
        "not_sub": "❗ Чтобы голосовать, сначала подпишитесь на канал!",
        "voted": "✅ Ваш голос принят!",
        "already": "Вы уже голосовали.",
        "closed": "🏁 Этот батл завершён.",
        "check_ask": "📊 <b>ПРОВЕРКА БАТЛА</b>\n\n📣 Перешлите пост с батлом из канала.\n\n❗ <i>Пересылайте только посты каналов!</i>\n\n❌ Отмена: /cancel",
        "check_none": "🔎 Батл не найден. Перешлите пост с батлом из канала.",
        "no_admin_battle": "Батлов, созданных вами как админом канала, пока нет.\n\nСделайте бота админом канала и напишите #batl — батл появится здесь.",
        "profile": (
            "👤 <b>Мой профиль</b>\n\n"
            "🆔 ID: <code>{id}</code>\n📛 Имя: {name}\n🔗 Username: {username}\n"
            "🌐 Язык: {lang}\n📆 Регистрация: {joined}\n\n"
            "🏆 Создано батлов: <b>{created}</b>\n🎯 Участвовал в батлах: <b>{joined_b}</b>\n"
            "🗳 Отдано голосов: <b>{given}</b>\n📥 Получено голосов: <b>{got}</b>"),
        "help": (
            "🎉 <b>Добро пожаловать в наш бот!</b>\n\n"
            "📌 <b>С помощью этого бота вы можете:</b>\n"
            "📣 Проводить голосовые конкурсы в своих каналах!\n"
            "🎖 Сделайте бота админом канала\n"
            "🥇 Напишите в канале #batl и всё готово ✅\n\n"
            "📌 <b>Преимущества</b>\n"
            "👥 Голосующие подписываются на ваш канал ✅\n"
            "❗ Если голосующий выйдет из канала, его голос автоматически снимается в реальном времени ✅"),
        "choose_lang": "🌐 Tilni tanlang / Choose language / Выберите язык:",
        "lang_set": "✅ Язык изменён.",
        "contact_ask": "✉️ Напишите сообщение, админ ответит.\n\n❌ Отмена: /cancel",
        "contact_sent": "✅ Ваше сообщение отправлено админу.",
        "finish": "⏹ Завершить",
        "delete": "🗑 Удалить",
        "back": "⬅️ Назад",
        "ends": "Окончание",
        "total": "Всего голосов",
        "winner": "🥇 Победитель",
        "draw": "🤝 Победитель не определён",
        "over": "🏁 Батл завершён",
        "votes": "голосов",
        "wait_pub": "напишите #batl в канале",
        "done": "✅ Готово.",
        "langname": "Русский",
    },
}
BTN_KEYS = ["create", "my", "check", "help", "profile", "lang", "contact"]


def key_of(text):
    for k in BTN_KEYS:
        for l in T:
            if T[l]["btn_" + k] == text:
                return k
    return None


# ----------------------------------------------------------------- helpers
states = {}  # user_id -> dict(step=..., ...)


def esc(s):
    return html.escape(str(s or ""))


def ulang(uid, fallback_code=None):
    r = one("SELECT lang FROM users WHERE id=?", (uid,))
    if r and r["lang"] in T:
        return r["lang"]
    if fallback_code:
        c = fallback_code[:2].lower()
        if c in ("ru", "en"):
            return c
    return "uz"


def upsert_user(u):
    if not one("SELECT 1 FROM users WHERE id=?", (u.id,)):
        lang = ulang(u.id, getattr(u, "language_code", None))
        run("INSERT INTO users(id,name,username,lang,joined) VALUES(?,?,?,?,?)",
            (u.id, (u.first_name or "") + (" " + u.last_name if u.last_name else ""),
             u.username or "", lang, int(time.time())))
    else:
        run("UPDATE users SET name=?, username=? WHERE id=?",
            ((u.first_name or "") + (" " + u.last_name if u.last_name else ""), u.username or "", u.id))


GREEN, BLUE, RED = "success", "primary", "danger"


class CKB(types.KeyboardButton):
    """Rangli reply tugma (Telegram 'style' maydoni)."""
    def __init__(self, text, style=None):
        super().__init__(text)
        self.style = style

    def to_dict(self):
        d = super().to_dict()
        if self.style:
            d["style"] = self.style
        return d


class CIB(types.InlineKeyboardButton):
    """Rangli inline tugma."""
    def __init__(self, text, style=None, **kw):
        super().__init__(text, **kw)
        self.style = style

    def to_dict(self):
        d = super().to_dict()
        if self.style:
            d["style"] = self.style
        return d


def main_kb(lang):
    t = T[lang]
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(CKB(t["btn_create"], GREEN), CKB(t["btn_my"], BLUE))
    kb.row(CKB(t["btn_check"], BLUE), CKB(t["btn_help"], GREEN))
    kb.row(CKB(t["btn_profile"], BLUE), CKB(t["btn_lang"], GREEN))
    kb.row(CKB(t["btn_contact"], RED))
    return kb


def cancel_kb():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(CKB("/cancel", RED))
    return kb


def fmt_ts(ts):
    return datetime.utcfromtimestamp(ts + TZ_OFFSET).strftime("%d.%m.%Y %H:%M")


def counts(b):
    opts = json.loads(b["options"])
    c = [0] * len(opts)
    for r in get("SELECT opt, COUNT(*) n FROM votes WHERE battle_id=? GROUP BY opt", (b["id"],)):
        if 0 <= r["opt"] < len(c):
            c[r["opt"]] = r["n"]
    return opts, c


def render(b):
    lang = ulang(b["owner"])
    t = T[lang]
    opts, c = counts(b)
    total = sum(c)
    lines = ["🏆 <b>%s</b>\n" % esc(b["title"])]
    for i, name in enumerate(opts):
        pct = (c[i] * 100 // total) if total else 0
        bar = "▓" * (pct // 10) + "░" * (10 - pct // 10)
        lines.append("%d. <b>%s</b>\n%s %d%% — %d %s" % (i + 1, esc(name), bar, pct, c[i], t["votes"]))
    lines.append("\n👥 %s: <b>%d</b>" % (t["total"], total))
    if b["status"] == "active" and b["end_ts"]:
        lines.append("⏳ %s: %s" % (t["ends"], fmt_ts(b["end_ts"])))
    elif b["status"] == "pending":
        lines.append("⏳ " + t["wait_pub"])
    elif b["status"] == "ended":
        lines.append("\n" + t["over"])
        top = max(c) if c else 0
        winners = [opts[i] for i in range(len(opts)) if c[i] == top]
        if top > 0 and len(winners) == 1:
            lines.append("%s: <b>%s</b>" % (t["winner"], esc(winners[0])))
        else:
            lines.append(t["draw"])
    return "\n".join(lines)


def vote_kb(b):
    opts, c = counts(b)
    kb = types.InlineKeyboardMarkup(row_width=1)
    for i, name in enumerate(opts):
        kb.add(CIB("%s — %d" % (name, c[i]), BLUE if i % 2 == 0 else GREEN,
                   callback_data="v:%d:%d" % (b["id"], i)))
    return kb


def refresh(bid):
    b = one("SELECT * FROM battles WHERE id=?", (bid,))
    if not b or not b["channel_id"] or not b["message_id"]:
        return
    try:
        bot.edit_message_text(render(b), b["channel_id"], b["message_id"],
                              reply_markup=vote_kb(b) if b["status"] == "active" else None)
    except Exception as e:
        if "not modified" not in str(e):
            logging.warning("refresh failed: %s", e)


def finish(bid):
    b = one("SELECT * FROM battles WHERE id=?", (bid,))
    if not b or b["status"] != "active":
        return
    run("UPDATE battles SET status='ended' WHERE id=?", (bid,))
    refresh(bid)
    try:
        bot.send_message(b["owner"], T[ulang(b["owner"])]["ended_owner"].format(title=esc(b["title"])))
    except Exception:
        pass


def timer_loop():
    while True:
        try:
            now = int(time.time())
            for b in get("SELECT id FROM battles WHERE status='active' AND end_ts IS NOT NULL AND end_ts<=?", (now,)):
                finish(b["id"])
        except Exception as e:
            logging.warning("timer: %s", e)
        time.sleep(20)


def fwd_info(m):
    fo = getattr(m, "forward_origin", None)
    if fo is not None and getattr(fo, "chat", None) is not None and getattr(fo, "message_id", None):
        return fo.chat.id, fo.message_id
    fc = getattr(m, "forward_from_chat", None)
    if fc is not None and getattr(m, "forward_from_message_id", None):
        return fc.id, m.forward_from_message_id
    return None


def send_menu(uid, lang, text=None):
    bot.send_message(uid, text or T[lang]["menu"], reply_markup=main_kb(lang))


# ----------------------------------------------------------------- private chat
@bot.message_handler(commands=["start"], chat_types=["private"])
def cmd_start(m):
    upsert_user(m.from_user)
    states.pop(m.from_user.id, None)
    lang = ulang(m.from_user.id)
    send_menu(m.chat.id, lang, T[lang]["welcome"])


@bot.message_handler(commands=["cancel"], chat_types=["private"])
def cmd_cancel(m):
    upsert_user(m.from_user)
    states.pop(m.from_user.id, None)
    send_menu(m.chat.id, ulang(m.from_user.id))


def show_my(uid, chat_id, lang):
    t = T[lang]
    rows = get("SELECT * FROM battles WHERE owner=? ORDER BY id DESC LIMIT 30", (uid,))
    if not rows:
        bot.send_message(chat_id, t["no_battles"])
        return
    kb = types.InlineKeyboardMarkup(row_width=1)
    for b in rows:
        kb.add(types.InlineKeyboardButton("%s  %s" % (t["st_" + b["status"]], b["title"]),
                                          callback_data="m:%d" % b["id"]))
    bot.send_message(chat_id, t["my_title"], reply_markup=kb)


def show_profile(m, lang):
    t = T[lang]
    u = one("SELECT * FROM users WHERE id=?", (m.from_user.id,))
    uid = m.from_user.id
    created = one("SELECT COUNT(*) n FROM battles WHERE owner=?", (uid,))["n"]
    joined_b = one("SELECT COUNT(DISTINCT battle_id) n FROM votes WHERE user_id=?", (uid,))["n"]
    given = one("SELECT COUNT(*) n FROM votes WHERE user_id=?", (uid,))["n"]
    got = one("SELECT COUNT(*) n FROM votes v JOIN battles b ON b.id=v.battle_id WHERE b.owner=?", (uid,))["n"]
    bot.send_message(m.chat.id, t["profile"].format(
        id=uid, name=esc(u["name"]), username=("@" + u["username"]) if u["username"] else "—",
        lang=T[lang]["langname"], joined=datetime.utcfromtimestamp(u["joined"] + TZ_OFFSET).strftime("%d.%m.%Y"),
        created=created, joined_b=joined_b, given=given, got=got))


def route_button(m, k, lang):
    t = T[lang]
    uid = m.from_user.id
    if k == "create":
        states[uid] = {"step": "title"}
        bot.send_message(m.chat.id, t["ask_title"], reply_markup=cancel_kb())
    elif k == "my":
        show_my(uid, m.chat.id, lang)
    elif k == "check":
        states[uid] = {"step": "check"}
        bot.send_message(m.chat.id, t["check_ask"], reply_markup=cancel_kb())
    elif k == "help":
        bot.send_message(m.chat.id, t["help"])
    elif k == "profile":
        show_profile(m, lang)
    elif k == "lang":
        kb = types.InlineKeyboardMarkup(row_width=1)
        kb.add(CIB("🇺🇿 O'zbekcha", GREEN, callback_data="l:uz"),
               CIB("🇬🇧 English", GREEN, callback_data="l:en"),
               CIB("🇷🇺 Русский", GREEN, callback_data="l:ru"))
        bot.send_message(m.chat.id, t["choose_lang"], reply_markup=kb)
    elif k == "contact":
        states[uid] = {"step": "contact"}
        bot.send_message(m.chat.id, t["contact_ask"], reply_markup=cancel_kb())


@bot.message_handler(chat_types=["private"],
                     content_types=["text", "photo", "video", "document", "audio", "voice", "sticker", "animation"])
def private_any(m):
    uid = m.from_user.id
    upsert_user(m.from_user)
    lang = ulang(uid)
    t = T[lang]
    text = (m.text or "").strip()

    # admin javobi (murojaatga reply)
    if uid == ADMIN_ID and m.reply_to_message and m.reply_to_message.text:
        mt = re.search(r"ID:\s*(\d+)", m.reply_to_message.text)
        if mt:
            try:
                bot.copy_message(int(mt.group(1)), m.chat.id, m.message_id)
                bot.send_message(m.chat.id, t["done"])
            except Exception as e:
                bot.send_message(m.chat.id, "⚠️ %s" % esc(e))
            return

    k = key_of(text)
    if k:
        states.pop(uid, None)
        route_button(m, k, lang)
        return

    st = states.get(uid)
    if not st:
        send_menu(m.chat.id, lang)
        return
    step = st["step"]

    if step == "title":
        if not text or len(text) > 60:
            bot.send_message(m.chat.id, t["bad_text"])
            return
        st["title"] = text
        st["step"] = "count"
        bot.send_message(m.chat.id, t["ask_count"])

    elif step == "count":
        if not text.isdigit() or not (2 <= int(text) <= 6):
            bot.send_message(m.chat.id, t["bad_number"])
            return
        st["n"] = int(text)
        st["opts"] = []
        st["step"] = "opt"
        bot.send_message(m.chat.id, t["ask_opt"].format(i=1, n=st["n"]))

    elif step == "opt":
        if not text or len(text) > 40:
            bot.send_message(m.chat.id, t["bad_text"])
            return
        st["opts"].append(text)
        if len(st["opts"]) < st["n"]:
            bot.send_message(m.chat.id, t["ask_opt"].format(i=len(st["opts"]) + 1, n=st["n"]))
        else:
            st["step"] = "hours"
            bot.send_message(m.chat.id, t["ask_hours"])

    elif step == "hours":
        if not text.isdigit() or not (1 <= int(text) <= 720):
            bot.send_message(m.chat.id, t["bad_number"])
            return
        run("INSERT INTO battles(owner,title,options,hours,status,created) VALUES(?,?,?,?, 'pending', ?)",
            (uid, st["title"], json.dumps(st["opts"], ensure_ascii=False), int(text), int(time.time())))
        states.pop(uid, None)
        send_menu(m.chat.id, lang, t["created"])

    elif step == "check":
        info = fwd_info(m)
        b = one("SELECT * FROM battles WHERE channel_id=? AND message_id=?", info) if info else None
        if not b:
            bot.send_message(m.chat.id, t["check_none"])
            return
        states.pop(uid, None)
        send_menu(m.chat.id, lang, render(b))

    elif step == "contact":
        u = m.from_user
        head = "📩 <b>Murojaat</b>\n👤 %s %s\nID: %d" % (esc(u.first_name), ("@" + u.username) if u.username else "", uid)
        try:
            bot.send_message(ADMIN_ID, head + ("\n\n" + esc(text) if text else ""))
            if not text:
                bot.copy_message(ADMIN_ID, m.chat.id, m.message_id)
        except Exception as e:
            logging.warning("contact: %s", e)
        states.pop(uid, None)
        send_menu(m.chat.id, lang, t["contact_sent"])


# ----------------------------------------------------------------- callbacks
@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("l:"))
def cb_lang(c):
    lang = c.data.split(":")[1]
    if lang not in T:
        return
    upsert_user(c.from_user)
    run("UPDATE users SET lang=? WHERE id=?", (lang, c.from_user.id))
    bot.answer_callback_query(c.id, T[lang]["lang_set"])
    try:
        bot.delete_message(c.message.chat.id, c.message.message_id)
    except Exception:
        pass
    send_menu(c.message.chat.id, lang, T[lang]["lang_set"])


def detail_kb(b, lang):
    t = T[lang]
    kb = types.InlineKeyboardMarkup(row_width=2)
    row = []
    if b["status"] == "active":
        row.append(CIB(t["finish"], BLUE, callback_data="f:%d" % b["id"]))
    row.append(CIB(t["delete"], RED, callback_data="d:%d" % b["id"]))
    kb.add(*row)
    kb.add(CIB(t["back"], None, callback_data="b:0"))
    return kb


@bot.callback_query_handler(func=lambda c: c.data and c.data[:2] in ("m:", "f:", "d:", "b:"))
def cb_battle(c):
    uid = c.from_user.id
    lang = ulang(uid, getattr(c.from_user, "language_code", None))
    t = T[lang]
    kind, bid = c.data.split(":")
    chat_id, mid = c.message.chat.id, c.message.message_id
    if kind == "b":
        bot.answer_callback_query(c.id)
        try:
            bot.delete_message(chat_id, mid)
        except Exception:
            pass
        show_my(uid, chat_id, lang)
        return
    b = one("SELECT * FROM battles WHERE id=? AND owner=?", (int(bid), uid))
    if not b:
        bot.answer_callback_query(c.id)
        return
    if kind == "m":
        bot.answer_callback_query(c.id)
        bot.edit_message_text(render(b), chat_id, mid, reply_markup=detail_kb(b, lang))
    elif kind == "f":
        finish(b["id"])
        bot.answer_callback_query(c.id, t["done"])
        b = one("SELECT * FROM battles WHERE id=?", (b["id"],))
        bot.edit_message_text(render(b), chat_id, mid, reply_markup=detail_kb(b, lang))
    elif kind == "d":
        if b["status"] == "active":
            finish(b["id"])
        run("DELETE FROM votes WHERE battle_id=?", (b["id"],))
        run("DELETE FROM battles WHERE id=?", (b["id"],))
        bot.answer_callback_query(c.id, t["done"])
        try:
            bot.delete_message(chat_id, mid)
        except Exception:
            pass
        show_my(uid, chat_id, lang)


@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("v:"))
def cb_vote(c):
    uid = c.from_user.id
    lang = ulang(uid, getattr(c.from_user, "language_code", None))
    t = T[lang]
    try:
        _, bid, idx = c.data.split(":")
        bid, idx = int(bid), int(idx)
    except Exception:
        return
    b = one("SELECT * FROM battles WHERE id=?", (bid,))
    if not b or b["status"] != "active":
        bot.answer_callback_query(c.id, t["closed"], show_alert=True)
        return
    if b["end_ts"] and b["end_ts"] <= time.time():
        finish(bid)
        bot.answer_callback_query(c.id, t["closed"], show_alert=True)
        return
    try:
        st = bot.get_chat_member(b["channel_id"], uid).status
    except Exception:
        st = "left"
    if st not in ("member", "administrator", "creator"):
        bot.answer_callback_query(c.id, t["not_sub"], show_alert=True)
        return
    if one("SELECT 1 FROM votes WHERE battle_id=? AND user_id=?", (bid, uid)):
        bot.answer_callback_query(c.id, t["already"], show_alert=True)
        return
    run("INSERT INTO votes(battle_id,user_id,opt,ts) VALUES(?,?,?,?)", (bid, uid, idx, int(time.time())))
    bot.answer_callback_query(c.id, t["voted"], show_alert=True)
    refresh(bid)


# ----------------------------------------------------------------- channel
@bot.channel_post_handler(content_types=["text"],
                          func=lambda m: (m.text or "").strip().lower().startswith("#batl"))
def on_batl(m):
    ch = m.chat.id
    try:
        admins = bot.get_chat_administrators(ch)
    except Exception as e:
        logging.warning("admins: %s", e)
        return
    ids = [a.user.id for a in admins if not a.user.is_bot]
    if not ids:
        return
    b = one("SELECT * FROM battles WHERE status='pending' AND owner IN (%s) ORDER BY id DESC LIMIT 1"
            % ",".join("?" * len(ids)), ids)
    if not b:
        return
    try:
        bot.delete_message(ch, m.message_id)
    except Exception:
        pass
    end_ts = int(time.time() + b["hours"] * 3600)
    run("UPDATE battles SET status='active', channel_id=?, channel_username=?, end_ts=? WHERE id=?",
        (ch, m.chat.username or "", end_ts, b["id"]))
    b = one("SELECT * FROM battles WHERE id=?", (b["id"],))
    sent = bot.send_message(ch, render(b), reply_markup=vote_kb(b))
    run("UPDATE battles SET message_id=? WHERE id=?", (sent.message_id, b["id"]))
    try:
        bot.send_message(b["owner"], T[ulang(b["owner"])]["published"].format(title=esc(b["title"])))
    except Exception:
        pass


@bot.chat_member_handler()
def on_member(u):
    new = u.new_chat_member.status
    if new not in ("left", "kicked"):
        return
    uid = u.new_chat_member.user.id
    for b in get("SELECT id FROM battles WHERE channel_id=? AND status='active'", (u.chat.id,)):
        if one("SELECT 1 FROM votes WHERE battle_id=? AND user_id=?", (b["id"], uid)):
            run("DELETE FROM votes WHERE battle_id=? AND user_id=?", (b["id"], uid))
            refresh(b["id"])


# ----------------------------------------------------------------- main
def keep_alive():
    """UptimeRobot uchun: oddiy veb-sahifa (qo'shimcha kutubxona kerak emas)."""
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class H(BaseHTTPRequestHandler):
        def _ok(self, body=True):
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            if body:
                self.wfile.write(b"OVOZ BATL bot is running")

        def do_GET(self):
            self._ok()

        def do_HEAD(self):
            self._ok(False)

        def log_message(self, *a):
            pass

    port = int(os.environ.get("PORT", "8080"))
    HTTPServer(("0.0.0.0", port), H).serve_forever()


if __name__ == "__main__":
    threading.Thread(target=keep_alive, daemon=True).start()
    threading.Thread(target=timer_loop, daemon=True).start()
    me = bot.get_me()
    logging.info("Bot ishga tushdi: @%s", me.username)
    bot.infinity_polling(allowed_updates=telebot.util.update_types, skip_pending=True, timeout=30)
