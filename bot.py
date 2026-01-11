from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)
import sqlite3
from datetime import datetime, time

# ---------------- BOT TOKEN ----------------
TOKEN ="8532526397:AAEggRPRSCvkMJRzTLOoW1bPz9rzzPA8MZI"
# ---------------- DATABASE ----------------
conn = sqlite3.connect("tasks.db", check_same_thread=False)
cur = conn.cursor()

# Permanent daily tasks
cur.execute("""
CREATE TABLE IF NOT EXISTS daily_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    task TEXT
)
""")

# Daily progress
cur.execute("""
CREATE TABLE IF NOT EXISTS daily_progress (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    task_id INTEGER,
    date TEXT,
    completed INTEGER
)
""")

# Streak table
cur.execute("""
CREATE TABLE IF NOT EXISTS streaks (
    user_id INTEGER PRIMARY KEY,
    streak INTEGER,
    last_day TEXT
)
""")

conn.commit()

# XP column
try:
    cur.execute(
        "ALTER TABLE streaks ADD COLUMN xp INTEGER DEFAULT 0"
    )
    conn.commit()
except sqlite3.OperationalError:pass

# ---------------- START ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⚔️ DAILY SYSTEM ACTIVATED ⚔️\n\n"
        "/add <task> - Add daily task\n"
        "/tasks - Show today's tasks\n"
        "/delete <number> - Delete task\n"
        "/streak - Show streak\n"
        "/stats - Stats\n\n"
        "Complete ALL tasks daily to maintain streak 🔥"
    )

# ---------------- ADD TASK ----------------
async def add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Use: /add Task name")
        return

    task = " ".join(context.args)
    user_id = update.effective_user.id

    cur.execute(
        "INSERT INTO daily_tasks (user_id, task) VALUES (?, ?)",
        (user_id, task)
    )
    conn.commit()

    await update.message.reply_text(f"✅ Daily task added:\n{task}")

# ---------------- ENSURE TODAY TASKS ----------------
def ensure_today_tasks(user_id):
    today = datetime.now().strftime("%Y-%m-%d")

    cur.execute(
        "SELECT id FROM daily_tasks WHERE user_id=?",
        (user_id,)
    )
    tasks = cur.fetchall()

    for (task_id,) in tasks:
        cur.execute("""
            SELECT 1 FROM daily_progress
            WHERE user_id=? AND task_id=? AND date=?
        """, (user_id, task_id, today))

        if not cur.fetchone():
            cur.execute("""
                INSERT INTO daily_progress
                (user_id, task_id, date, completed)
                VALUES (?, ?, ?, 0)
            """, (user_id, task_id, today))

    conn.commit()

# ---------------- SHOW TASKS ----------------
async def tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    today = datetime.now().strftime("%Y-%m-%d")

    ensure_today_tasks(user_id)

    cur.execute("""
        SELECT dp.id, dt.task
        FROM daily_progress dp
        JOIN daily_tasks dt ON dp.task_id = dt.id
        WHERE dp.user_id=? AND dp.date=? AND dp.completed=0
    """, (user_id, today))

    rows = cur.fetchall()

    if not rows:
        await update.message.reply_text("🎉 All tasks completed today!")
        return

    for prog_id, task_text in rows:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Done", callback_data=f"done_{prog_id}")]
        ])
        await update.message.reply_text(task_text, reply_markup=keyboard)

# ---------------- DONE BUTTON ----------------
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    prog_id = int(query.data.split("_")[1])
    user_id = query.from_user.id
    today = datetime.now().strftime("%Y-%m-%d")

    cur.execute(
        "UPDATE daily_progress SET completed=1 WHERE id=?",
        (prog_id,)
    )
    conn.commit()

    cur.execute(
    "UPDATE streaks SET xp = COALESCE(xp, 0) + 10 WHERE user_id=?",
    (user_id,)
    )
    conn.commit()

    await query.edit_message_text("✅ Task completed")
# Check if all done
    cur.execute("""
        SELECT COUNT(*) FROM daily_progress
        WHERE user_id=? AND date=? AND completed=0
    """, (user_id, today))

    remaining = cur.fetchone()[0]

    if remaining == 0:
        await system_message(
            context,
            user_id,
            "All daily quests completed.\nAwaiting daily evaluation."
            )

        cur.execute(
            "SELECT streak FROM streaks WHERE user_id=?",
            (user_id,)
        )
        row = cur.fetchone()
        streak = row[0] + 1 if row else 1
        
        cur.execute(
            "UPDATE streaks SET xp = COALESCE(xp,0) + 30 WHERE user_id=?",
            (user_id)
        )

        cur.execute("SELECT 1 FROM streaks WHERE user_id=?", (user_id,))
        exists = cur.fetchone()

        if exists:
           cur.execute(
           "UPDATE streaks SET streak=?, last_day=? WHERE user_id=?",
           (streak, today, user_id)
        )
        else:
           cur.execute(
           "INSERT INTO streaks (user_id, streak, last_day, xp) VALUES (?, ?, ?, 0)",
           (user_id, streak, today)
        )

        await system_message(
            context,
            user_id,
            f"Daily quest cleared.\nStreak increased to {streak} day(s)."
        )

conn.commit()

# ---------------- STREAK ----------------
async def streak(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id

    cur.execute(
        "SELECT streak, xp FROM streaks WHERE user_id=?",
        (user_id,)
    )
    row = cur.fetchone()

    if row:
        streak, xp = row
    else:
        streak, xp = 0, 0

    await update.message.reply_text(
        f"🔥 Streak: {streak} days\n"
        f"⚡ XP: {xp}"
    )


# --------------- STREAK BREAKER -------------
async def streak_breaker(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now()
    NIGHT_TIME = "04:59"   # change if you want

    if now.strftime("%H:%M") < NIGHT_TIME:
        return

    today = now.strftime("%Y-%m-%d")

    cur.execute("SELECT DISTINCT user_id FROM daily_tasks")
    users = cur.fetchall()

    for (user_id,) in users:
        cur.execute("""
            SELECT COUNT(*) FROM daily_progress
            WHERE user_id=? AND date=? AND completed=0
        """, (user_id, today))

        remaining = cur.fetchone()[0]

        if remaining > 0:
            # BREAK STREAK
            cur.execute("""
                UPDATE streaks
                SET streak=0, last_day=?
                WHERE user_id=?
            """, (today, user_id))
            conn.commit()

            await context.bot.send_message(
                chat_id=user_id,
                text="💀 STREAK BROKEN\nYou failed to complete all daily tasks."
            )
            await system_message(
    context,
    user_id,
    "Quest failed.\nYou did not complete all daily tasks.\nStreak reset to 0."
)

# ---------------- SYSTEM MESSAGE ------------
async def system_message(context, user_id, text):
    await context.bot.send_message(
        chat_id=user_id,
        text=f"🖥️ [SYSTEM]\n{text}"
    )
# ---------------- DELETE TASK ----------------
async def delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Use: /delete <number>")
        return

    user_id = update.effective_user.id
    num = int(context.args[0])

    cur.execute(
        "SELECT id FROM daily_tasks WHERE user_id=? ORDER BY id",
        (user_id,)
    )
    tasks = cur.fetchall()

    if num < 1 or num > len(tasks):
        await update.message.reply_text("❌ Invalid task number")
        return

    task_id = tasks[num - 1][0]

    cur.execute("DELETE FROM daily_tasks WHERE id=?", (task_id,))
    cur.execute("DELETE FROM daily_progress WHERE task_id=?", (task_id,))
    conn.commit()

    await update.message.reply_text("🗑 Task deleted permanently")

# ---------------- STATS ----------------
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    cur.execute(
        "SELECT COUNT(*) FROM daily_tasks WHERE user_id=?",
        (user_id,)
    )
    total = cur.fetchone()[0]

    cur.execute(
        "SELECT COUNT(*) FROM daily_progress WHERE user_id=? AND completed=1",
        (user_id,)
    )
    completed = cur.fetchone()[0]

    await update.message.reply_text(
        f"📊 Stats\n\n"
        f"📋 Daily tasks: {total}\n"
        f"✅ Total completions: {completed}"
    )

# ---------------- DAILY REMINDER ----------------
async def daily_reminder(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now()
    if now.strftime("%H:%M") != "05:00":
        return

    cur.execute("SELECT DISTINCT user_id FROM daily_tasks")
    users = cur.fetchall()

    for (user_id,) in users:
        ensure_today_tasks(user_id)

        cur.execute("""
            SELECT dt.task
            FROM daily_progress dp
            JOIN daily_tasks dt ON dp.task_id=dt.id
            WHERE dp.user_id=? AND dp.date=? AND dp.completed=0
        """, (user_id, now.strftime("%Y-%m-%d")))

        tasks = cur.fetchall()

        if tasks:
            msg = "⏰ DAILY QUESTS:\n\n"
            for i, (t,) in enumerate(tasks, 1):
                msg += f"{i}. {t}\n"

            await context.bot.send_message(chat_id=user_id, text=msg)
            await system_message(
    context,
    user_id,
    "New day has begun.\nDaily quests have been assigned."
)

# ---------------- MAIN ----------------
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add", add))
    app.add_handler(CommandHandler("tasks", tasks))
    app.add_handler(CommandHandler("delete", delete))
    app.add_handler(CommandHandler("streak", streak))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CallbackQueryHandler(button_handler))

    app.job_queue.run_repeating(streak_breaker, interval=60, first=10)
    app.job_queue.run_repeating(daily_reminder, interval=60, first=10)

    print("⚔️ SYSTEM RUNNING ⚔️")
    app.run_polling()

if __name__ == "__main__":
    main()