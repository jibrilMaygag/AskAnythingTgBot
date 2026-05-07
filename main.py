from telegram import Update
from telegram.ext import Application,CommandHandler,filters,ContextTypes,CallbackQueryHandler,MessageHandler
from config import TOKEN
from handlers.start import start
from handlers.buttons import button_handler
from handlers.message import message_handler


async def help_command(update:Update,context:ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("I am waydii somali")

async def waydi_command(update:Update,context:ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("soo dhig suaasha")

async def error(update:Update,context:ContextTypes.DEFAULT_TYPE):
    print(f"update: {update} caused error {context.error}")



if __name__ == '__main__':
    print("strting the bot")
    app = Application.builder().token(TOKEN).build()

    # commands
    app.add_handler(CommandHandler('start',start))
    app.add_handler(CommandHandler('help',help_command))
    app.add_handler(CommandHandler('waydii',waydi_command))

    # callback handlers
    app.add_handler(CallbackQueryHandler(button_handler))

    # normal text messages
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    #errors
    
    app.add_error_handler(error)

    # polls the bot
    print("polling")
    app.run_polling(poll_interval=2)
    