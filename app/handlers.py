import datetime
from googleapiclient.discovery import build
from oauth2client.client import OAuth2WebServerFlow, FlowExchangeError
from oauth2client.file import Storage
import httplib2
import sys
import os
import json
from app import bot, SCOPES
import logging
import maya
from pendulum.parsing.exceptions import ParserError
from dateutil.relativedelta import relativedelta

UTC_TIME = 'Z'
TIMEZONE_LEN = 7
DATE_LEN = 10
MAX_NUM_EVENTS = 100
CREDENTIALS_FOLDER_PATH = './credentials'


def bot_error_decorator(func):
    def wrapper(message, *args, **kwargs):
        try:
            func(message, *args, **kwargs)
        except Exception:
            # Check if we have problem with sending a message
            try:
                bot.send_message(message.chat.id, 'Unknown error')
            except Exception:
                logging.error(sys.exc_info())
            logging.error(sys.exc_info())
    return wrapper


def get_credentials(chat_id):
    # Get credentials from file
    storage = Storage('{folder_path}/credentials-{id}.dat'.format(folder_path=CREDENTIALS_FOLDER_PATH,
                                                                  id=chat_id))
    return storage.get()


def save_credentials(chat_id, credentials):
    # Save credentials to file
    storage = Storage('{folder_path}/credentials-{id}.dat'.format(folder_path=CREDENTIALS_FOLDER_PATH,
                                                                  id=chat_id))
    storage.put(credentials)


def refresh_get_credentials(chat_id):
    # Get old credentials
    credentials = get_credentials(chat_id)
    if credentials is None:
        return None

    # Refresh access token for credentials
    credentials.refresh(httplib2.Http())
    return credentials


def list_of_events_from_period(credentials, start_date, end_date=None, max_events=MAX_NUM_EVENTS):
    # Launch calendar API interactor
    service = build('calendar', 'v3', credentials=credentials)

    # Call the Calendar API
    if end_date is None:
        events_result = service.events().list(calendarId='primary',
                                              timeMin=start_date.isoformat()[:-TIMEZONE_LEN] + UTC_TIME,
                                              maxResults=max_events, singleEvents=True,
                                              orderBy='startTime').execute()
    else:
        events_result = service.events().list(calendarId='primary',
                                              timeMax=end_date.isoformat()[:-TIMEZONE_LEN] + UTC_TIME,
                                              timeMin=start_date.isoformat()[:-TIMEZONE_LEN] + UTC_TIME,
                                              maxResults=max_events, singleEvents=True,
                                              orderBy='startTime').execute()

    # Get list of events
    events = events_result.get('items', [])
    events_text = []
    if not events:
        events_text.append('No events found')
    for event in events:
        # Parse event
        message_text = parse_event(event)

        # Append full message
        events_text.append(message_text)
    return events_text


def parse_event(event):
    # Try to get time in dateTime format
    date = event['start'].get('dateTime')

    # Array with parts of message
    message_arr = []
    if date is None:
        # Get time in only date format
        date = event['start'].get('date')
        if date is None:
            message_arr.append('No date - ')
        else:
            dt = maya.parse(date).datetime()
            message_arr.append('{date} '.format(date=dt.date()))
    else:
        dt = maya.parse(date).datetime()
        message_arr.append('{date} {time} {timezone} '.format(
            date=dt.date(), time=dt.time(), timezone=dt.tzinfo))

    # Append information about event
    message_arr.append('{summary}'.format(summary=event['summary']))
    return ''.join(message_arr)


@bot.message_handler(commands=['start'])
@bot_error_decorator
def handle_start(message):
    bot.send_message(message.chat.id, 'Hi! Firstly, you need to log in\nSend /reg command\n'
                                      'After registration send /help to get list of available commands')


@bot.message_handler(commands=['help'])
@bot_error_decorator
def handle_help(message):
    if get_credentials(message.chat.id) is None:
        bot.send_message(message.chat.id, 'Firstly, you need to log in\nSend /reg command')
        return
    bot.send_message(message.chat.id, 'List of available commands\n'
                                      '/near "n"\n'
                                      '  Send list of "n" nearest events\n'
                                      '  0 < "n" <= {max_events}\n'
                                      '/last "n"\n'
                                      '  Send list of "n" events from the month ago\n'
                                      '  0 < "n" <= {max_events}\n'
                                      '/period "YYYY-MM-DD" - "YYYY-MM-DD"\n'
                                      '  Send list of events from selected period\n'
                                      '  Send {max_events} from this period\n'
                                      '/day\n'
                                      '  Send list of events for today\n'
                                      '/day "YYYY-MM-DD"\n'
                                      '  Send list of events for selected day\n'
                                      '/delete\n'
                                      '  Delete your authentication info'.format(max_events=MAX_NUM_EVENTS))


@bot.message_handler(commands=['delete'])
@bot_error_decorator
def handle_delete_message(message):
    if get_credentials(message.chat.id) is None:
        bot.send_message(message.chat.id, 'Credentials are do not exist')
        return

    # Delete user credential
    os.remove('{folder_path}/credentials-{id}.dat'.format(folder_path=CREDENTIALS_FOLDER_PATH,
                                                          id=message.chat.id))

    bot.send_message(message.chat.id, 'Your credentials are deleted')


@bot.message_handler(commands=['reg'])
@bot_error_decorator
def handle_reg_message(message):
    if get_credentials(message.chat.id) is not None:
        bot.send_message(message.chat.id, 'You are already log in\n'
                                          'Send /help to get list of available commands')
        return
    bot.send_message(message.chat.id, 'Starting authentication')

    # Getting app credentials from file
    with open('credentials.json', 'r') as f:
        cred = json.load(f)['installed']

    # Init auth flow
    flow = OAuth2WebServerFlow(client_id=cred['client_id'],
                               client_secret=cred['client_secret'],
                               scope=SCOPES, redirect_uri=cred['redirect_uris'][0])

    # Getting authentication url
    auth_url = flow.step1_get_authorize_url()
    bot.send_message(message.chat.id, '{} - Authorization_url'.format(auth_url))
    bot.send_message(message.chat.id, 'Write here your authentication token')

    # Receive message with auth code
    bot.register_next_step_handler(message, lambda m: get_auth_token(m, flow))


@bot_error_decorator
def get_auth_token(message, flow):
    try:
        # Get auth code from message
        code = message.text

        # Get credentials from google server
        credentials = flow.step2_exchange(code)

        # Save credentials to the file
        save_credentials(message.chat.id, credentials)

        bot.send_message(message.chat.id, 'End of authentication')
    except Exception as err:
        if isinstance(err, FlowExchangeError):
            bot.send_message(message.chat.id, 'Incorrect authentication code')
        else:
            raise


@bot.message_handler(commands=['near'])
@bot_error_decorator
def upcoming_events(message):
    credentials = refresh_get_credentials(message.chat.id)
    if credentials is None:
        bot.send_message(message.chat.id, 'You need to log in first\nSend /reg command')
        return

    # Checking correctness of incoming message
    try:
        com_len = len('/near ')
        if message.text[com_len:] == '':
            number_of_events = MAX_NUM_EVENTS
        else:
            number_of_events = int(message.text[com_len:])
    except ValueError:
        bot.send_message(message.chat.id, 'Incorrect number, you should write only a number')
        return
    if number_of_events <= 0:
        bot.send_message(message.chat.id, 'Incorrect number of events')
        return
    if number_of_events > MAX_NUM_EVENTS:
        bot.send_message(message.chat.id, 'Too much events')
        return

    # Getting current time
    now = datetime.datetime.utcnow()

    bot.send_message(message.chat.id, 'Getting {} upcoming events'.format(number_of_events))

    # Gets upcoming events
    events_text = list_of_events_from_period(credentials, now, max_events=number_of_events)

    bot.send_message(message.chat.id, '\n'.join(events_text))


@bot.message_handler(commands=['last'])
@bot_error_decorator
def last_events(message):
    credentials = refresh_get_credentials(message.chat.id)
    if credentials is None:
        bot.send_message(message.chat.id, 'You need to log in first\nSend /reg command')
        return

    # Checking correctness of incoming message
    try:
        com_len = len('/last ')
        if message.text[com_len:] == '':
            number_of_events = MAX_NUM_EVENTS
        else:
            number_of_events = int(message.text[com_len:])
    except ValueError:
        bot.send_message(message.chat.id, 'Incorrect number, you should write only a number')
        return

    if number_of_events <= 0:
        bot.send_message(message.chat.id, 'Incorrect number of events')
        return
    if number_of_events > MAX_NUM_EVENTS:
        bot.send_message(message.chat.id, 'Too much events')
        return

    # Configure time borders
    today = datetime.datetime.today()
    month_ago = today - relativedelta(months=1)

    bot.send_message(message.chat.id, 'Getting {} events from last month'.format(number_of_events))
    
    # Gets events for month
    events_text = list_of_events_from_period(credentials, month_ago, today, number_of_events)

    bot.send_message(message.chat.id, '\n'.join(events_text))


@bot.message_handler(commands=['day'])
@bot_error_decorator
def day_events(message):
    credentials = refresh_get_credentials(message.chat.id)
    if credentials is None:
        bot.send_message(message.chat.id, 'You need to log in first\nSend /reg command')
        return

    # Parse incoming message
    com_len = len('/day ')
    period = message.text[com_len:]
    start_date = period[:DATE_LEN]

    # Checking correctness of incoming message
    if period == '':
        start_date = datetime.datetime.today().date()
    try:
        start_date = maya.parse(start_date).datetime()
    except ParserError:
        bot.send_message(message.chat.id, 'Incorrect format of the date')
        return
    end_date = start_date + relativedelta(days=1)
    
    bot.send_message(message.chat.id, 'List of events for {}'.format(start_date.date()))
    
    # Get events for current date
    events_text = list_of_events_from_period(credentials, start_date, end_date)
    
    # Get rid of date because we look for definite date
    for i, event in enumerate(events_text):
        if event[0].isdigit():
            events_text[i] = event[DATE_LEN:]
    bot.send_message(message.chat.id, '\n'.join(events_text))


@bot.message_handler(commands=['period'])
@bot_error_decorator
def period_events(message):
    credentials = refresh_get_credentials(message.chat.id)
    if credentials is None:
        bot.send_message(message.chat.id, 'You need to log in first\nSend /reg command')
        return

    # Parse incoming message
    com_len = len('/period ')
    period = message.text[com_len:]
    start_date = period[:DATE_LEN]
    end_date = period[-DATE_LEN:]
    
    # Checking correctness of incoming message
    if start_date == '':
        bot.send_message(message.chat.id, 'You should write correct date')
        return
    try:
        start_date = maya.parse(start_date).datetime()
    except ParserError:
        bot.send_message(message.chat.id, 'Incorrect format of the first date')
        return
    try:
        end_date = maya.parse(end_date).datetime()
    except ParserError:
        bot.send_message(message.chat.id, 'Incorrect format of the second date')
        return
    if end_date < start_date:
        bot.send_message(message.chat.id, 'Second date is bigger that first date')
        return

    bot.send_message(message.chat.id, 'Events since {} to {}'.format(start_date.date(), end_date.date()))

    # Get events from selected period
    events_text = list_of_events_from_period(credentials, start_date, end_date)

    bot.send_message(message.chat.id, '\n'.join(events_text))


@bot.message_handler(content_types=['text'])
def handle_text_message(message):
    # When gets random text redirect to help command
    handle_help(message)
