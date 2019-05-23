import telebot


bot = None
SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']


def init_bot(token):
    global bot
    bot = telebot.TeleBot(token)
    from app import handlers
