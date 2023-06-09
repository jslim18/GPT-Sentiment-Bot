import asyncio
import os
import datetime
import json
import requests
import time
import pytz
import openai
from openai import InvalidRequestError
from typing import Dict, Any
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, executor
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.types import ParseMode
from aiogram.utils import executor
from apscheduler.schedulers.asyncio import AsyncIOScheduler

load_dotenv()

EOD_API_KEY = "MAKEYOUROWNKEY"#os.getenv("EOD_API_KEY")
OPENAI_API_KEY = "MAKEYOUROWNKEY"#os.getenv("OPENAI_API_KEY")
TELEGRAM_BOT_TOKEN = "MAKEYOUROWNKEY"#os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = "MAKEYOUROWNKEY"#os.getenv("TELEGRAM_CHAT_ID")


openai.api_key = OPENAI_API_KEY

bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher(bot)
dp.middleware.setup(LoggingMiddleware())

async def on_startup(dp):
    await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text="Bot has been started")

async def on_shutdown(dp, scheduler):
    await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text="Bot has been stopped")

    # Remove all handlers
    dp.message_handlers.clear()

    # Close bot and dispatcher
    await dp.storage.close()
    await dp.storage.wait_closed()

    # Close scheduler
    scheduler.shutdown()

    # Close connections
    await bot.session.close()

# Command handlers
import requests

import requests

@dp.message_handler(commands=['help'])
async def help(message: types.Message):
    message_text = ("Here are the available commands:\n\n"
                    "/get_list_sentiments - Run sentiment analysis on stocks being tracked.\n\n"
                    "/list_companies - List all the companies currently being tracked.\n\n"
                    "/add_company <company_ticker or comma-separated list of tickers> Add a company or multiple to the tracking list. Replace <company_ticker> with the actual stock ticker.\n\n"
                    "Example: /add_company MSFT.US, TSLA.US, SBUX.US\n\n"
                    "/remove_company <company_ticker> - Remove a company from the tracking list. Replace <company_ticker> with the stock ticker.\n\n"
                    "/get_sentiment <comma-separated list of tickers> - Get sentiments for a list of companies that may or may not be in your list.\n"
                    "Example: /get_sentiment AAPL.US, MSFT.US, TSLA.US\n\n"
                    "\nOther Examples:\n"
                    "/add_company AAPL.US\n"
                    "/remove_company APPL.US")
    await message.reply(message_text)


def parse_companies_input(input_str: str) -> Dict[str, str]:
    companies = {}
    company_pairs = input_str.split(';')
    for pair in company_pairs:
        pair_items = pair.split(',')
        if len(pair_items) != 2:
            continue
        symbol = pair_items[0].strip().upper()
        name = pair_items[1].strip()
        companies[symbol] = name
    return companies


## ISSUE 1
def check_openai_connection():
    try:
        response = requests.get("https://api.openai.com/v1/models", headers={"Authorization": f"Bearer {OPENAI_API_KEY}"})
        response.raise_for_status()
        return "[PASS]"
    except requests.exceptions.RequestException:
        return "[FAIL]"

def check_eodhd_connection():
    try:
        response = requests.get(f"https://eodhistoricaldata.com/api/news?api_token={EOD_API_KEY}&limit=1")
        response.raise_for_status()
        return "[PASS]"
    except requests.exceptions.RequestException:
        return "[FAIL]"
    
    
@dp.message_handler(commands=['get_status'])
async def get_status(message: types.Message):
    openai_status = check_openai_connection()
    eodhd_status = check_eodhd_connection()

    status_message = (
        f"Connection OpenAI: {openai_status}\n"
        f"Connection EODHD: {eodhd_status}\n"
    )

    await message.reply(status_message)
## /ISSUE1

## ISSUE 2
    
#
def load_ticker_list():
    default_companies = {
        "AAPL.US": "Apple Inc. US",
    }

    if not os.path.exists("tickers.json"):
        return default_companies

    with open("tickers.json", "r") as f:
        loaded_companies = json.load(f)

    # Merge the default_companies with loaded_companies
    merged_companies = {**default_companies, **loaded_companies}
    return merged_companies

def save_ticker_list(companies):
    with open("tickers.json", "w") as f:
        json.dump(companies, f)

COMPANIES = load_ticker_list()

#
def verify_symbol(symbol):
    # Remove this if-statement if you want to allow no-dot notation (e.g. AAPL)
    if symbol.count(".") != 1:
        return False
    
    API_URL = f"https://eodhistoricaldata.com/api/news?api_token={EOD_API_KEY}&s={symbol}&&limit=10"

    response = requests.get(API_URL)
    data = response.json()

    if data:  # Check if the response has any data (i.e., the symbol exists)
        return True
    return False

#
@dp.message_handler(commands=['add_company'])
async def add_company(message: types.Message):
    input_symbols = message.get_args().split(",")
    symbols = [symbol.upper() for symbol in input_symbols]

    COMPANIES = load_ticker_list()

    added_symbols = []
    existing_symbols = []
    invalid_symbols = []

    for symbol in symbols:
        if symbol in COMPANIES:
            existing_symbols.append(symbol)
        else:
            if verify_symbol(symbol):
                COMPANIES[symbol] = ""  # No company name is stored
                added_symbols.append(symbol)
            else:
                invalid_symbols.append(symbol)

    save_ticker_list(COMPANIES)

    response_text = ""
    if added_symbols:
        response_text += f"Added {', '.join(added_symbols)} to the list."
    if existing_symbols:
        response_text += f"\n{', '.join(existing_symbols)} already exist in the list."
    if invalid_symbols:
        response_text += f"\n{', '.join(invalid_symbols)} are not valid symbols."

    await message.reply(response_text.strip())

@dp.message_handler(commands=['remove_company'])
async def remove_company(message: types.Message):
    symbol = message.get_args().split()[0].upper()

    COMPANIES = load_ticker_list()

    if symbol not in COMPANIES:
        await message.reply(f"{symbol} is not in the list.")
    else:
        COMPANIES.pop(symbol)
        save_ticker_list(COMPANIES)
        await message.reply(f"Removed {symbol} from the list.")

#
@dp.message_handler(commands=['list_companies'])
async def list_companies(message: types.Message):
    COMPANIES = load_ticker_list()  # Load the latest ticker list from the JSON file
    if not COMPANIES:
        await message.reply("No companies in the list.")
    else:
        company_list = "\n".join([f"{symbol}" for symbol in COMPANIES.keys()])
        await message.reply(f"List of companies:\n{company_list}")

@dp.message_handler(commands=['get_list_sentiments'])
async def get_sentiments(message: types.Message):
    COMPANIES = load_ticker_list()  # Load the latest ticker list from the JSON file

    if not COMPANIES:
        await message.reply("The list of companies is empty.")
    else:
        await analyze_sentiments_for_companies(COMPANIES)
        
#
async def analyze_sentiments_for_companies(companies, header_amount=-100):
    headlines = get_news_headlines_for_companies(companies, header_amount)
    sentiment_scores = {}

    for company, company_headlines in headlines.items():
        num_headlines = len(company_headlines)
        print(f"{company}: {num_headlines} headlines")

        if num_headlines == 0:
            sentiment_scores[company] = "0 headlines"
            await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=f"No headlines.")
            break
        else:
            scores = []
            for headline in company_headlines:
                print("Sending headline for analysis")
                for _ in range(3):
                    try:
                        sentiment = perform_sentiment_analysis(company, headline["title"])
                        break
                    except openai.error.RateLimitError:
                        time.sleep(2)
                else:
                    sentiment = "Neutral"
                score = assign_sentiment_score(sentiment)
                scores.append(score)
            # I believe the sentiment analysis is flawed, it doesn't give accurate answers from a test I did
            # Also, the response from the API already has a pre-made sentiment analysis in 'headline'
            # Also, also, it's possible for the sentiment score to go below 0, if you don't want that I recommend that
            # you change the values to Positive: 1, Neutral: 0.5, Negative: 0, Else: 0.5
            average_score = sum(scores) / len(scores) if scores else 0
            sentiment_scores[company] = company_headlines, round(average_score, 2)
    else:
        await send_summary_message(sentiment_scores)

def get_news_headlines_for_companies(companies: Dict[str, str], header_amount=-100):
    headlines = {}
    for symbol in companies.keys():
        url = f"https://eodhistoricaldata.com/api/news?api_token={EOD_API_KEY}&s={symbol}&&limit={abs(header_amount)}"

        response = requests.get(url)

        try:
            all_headlines = response.json()
        except json.JSONDecodeError:
            print(f"Error decoding JSON for {symbol}: {response.content}")
            all_headlines = []

        if header_amount < 0:
            est = pytz.timezone("US/Eastern")
            utc = pytz.UTC

            start_time = datetime.datetime.strptime(yesterday_9am_est(), "%Y-%m-%d %H:%M:%S").replace(tzinfo=est).astimezone(utc)
            end_time = datetime.datetime.strptime(today_9am_est(), "%Y-%m-%d %H:%M:%S").replace(tzinfo=est).astimezone(utc)

            filtered_headlines = [headline for headline in all_headlines if start_time <= datetime.datetime.strptime(headline["date"], "%Y-%m-%dT%H:%M:%S%z") <= end_time]
        else:
            filtered_headlines = all_headlines

        headlines[symbol] = filtered_headlines

    return headlines

def today_9am_est():
    return datetime.datetime.now(pytz.timezone("US/Eastern")).replace(hour=9, minute=25, second=0, microsecond=0).strftime("%Y-%m-%d %H:%M:%S")

def yesterday_9am_est():
    return (datetime.datetime.now(pytz.timezone("US/Eastern")) - datetime.timedelta(days=1)).replace(hour=9, minute=31, second=0, microsecond=0).strftime("%Y-%m-%d %H:%M:%S")

def perform_sentiment_analysis(company,  headline):
    print(headline)
    try:
        response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "user", "content": f"Forget all your previous instructions. Pretend you are a financial expert. You are a financial expert with stock recommendation experience. Answer “Positive” if good news, “Negative” if bad news, or “Neutral” if uncertain in the first line. Provide no other context. Is this headline good or bad for the stock price of {company} in the short term? \n Headline: {headline}" }
        ],
        temperature=0.2,
        )
    except InvalidRequestError as e:
        return f"Error: {e}"
    
    sentiment = response["choices"][0]["message"]["content"]
    print(sentiment)
    return sentiment

def assign_sentiment_score(sentiment):
    sentiment = sentiment.lower()
    if "positive" in sentiment:
        return 1
    elif "neutral" in sentiment:
        return 0
    elif "negative" in sentiment:
        return -1
    else:
        return 0

## ISSUE 3
async def send_summary_message(sentiment_scores):
    message = "Daily Stock Sentiment\nSummary:\n"
    for company, score in sentiment_scores.items():
        message += f"{company}: {score[1]}\n\n"

        dates = []
        for headline in score[0]:
            date_string = headline["date"]
            datetime_obj = datetime.datetime.strptime(date_string, "%Y-%m-%dT%H:%M:%S%z")
            formatted_date = datetime_obj.strftime("%y-%m-%d %H:%M")
            dates.append(datetime_obj)

        dates_headlines = sorted(tuple(zip(dates, score[0])))

        for date_headline in dates_headlines:
            formatted_date = date_headline[0].strftime("%y-%m-%d %H:%M")
            message += f"{formatted_date}: {date_headline[1]['title']}\n"

        message += "\n"
        
    await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
## /ISSUE 3

@dp.message_handler(commands=['get_sentiment'])
async def get_sentiment(message: types.Message):
    header_amount = 100
    
    symbols = []
    
    symbols_arg = message.get_args().split("-")
    
    if len(symbols_arg) == 1:
        symbols_arg.append("R") # By default, only the recent headlines are shown
        
    for symbol_arg in symbols_arg[1:]:
        symbol_arg = symbol_arg.strip()
        if symbol_arg.upper() == "R":
            header_amount = -abs(header_amount)
        elif symbol_arg[:1].upper() == "H:":
            if symbol_arg[:1] != symbol_arg:
                try:
                    header_amount = int(header_amount/abs(header_amount)*int(symbol_arg.split(":")[1]))
                except ValueError:
                    pass
        else:
            await message.reply(f"Invalid option '-{symbol_arg}'.")
            return
        
    symbols = [symbol.strip().upper() for symbol in symbols_arg[0].split(',')]

    companies = {}

    if not symbols:
        await message.reply("Please provide at least one company symbol separated by commas.")
    else:
        for symbol in symbols:
            if verify_symbol(symbol):
                companies[symbol] = ""  # No company name is stored
            else:
                await message.reply(f"The symbol '{symbol}' is invalid.")
                break
        else:   
            await analyze_sentiments_for_companies(companies, header_amount)

async def wrapped_analyze_sentiments():
    await analyze_sentiments_for_companies(COMPANIES)

async def run_scheduler():
    scheduler = AsyncIOScheduler()

    # Schedule analyze_sentiments_for_companies() to run from Monday to Friday at 9 AM US/Eastern
    scheduler.add_job(lambda: asyncio.create_task(analyze_sentiments_for_companies(COMPANIES)), "cron", day_of_week="mon-fri", hour=9, minute=0, timezone="US/Eastern")

    # Start the scheduler
    await scheduler.start()

## /ISSUE 2


def main():
    from aiogram import executor

    # Schedule analyze_sentiments_for_companies() to run from Monday to Friday at 9 AM US/Eastern
    scheduler = AsyncIOScheduler()
    scheduler.add_job(wrapped_analyze_sentiments, "cron", day_of_week="mon-fri", hour=9, minute=0, timezone="US/Eastern")
    scheduler.start()

    executor.start_polling(dp, on_startup=on_startup, on_shutdown=on_shutdown, skip_updates=True)


if __name__ == '__main__':
    main()
