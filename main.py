from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, CallbackQuery, KeyboardButton
from aiogram.utils.deep_linking import get_start_link, decode_payload
import aiohttp
import logging
from emoji import emojize
import shelve
import os
import traceback
import pymysql
import atexit
import config
from time import sleep

log = os.path.join('LOG.txt')

logger = logging.getLogger("BOT")
logger.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
eh = logging.FileHandler(log)
ch.setLevel(logging.DEBUG)
eh.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(module)s - %(levelname)s - %(message)s')
eh.setFormatter(formatter)
ch.setFormatter(formatter)

logger.addHandler(eh)
logger.addHandler(ch)


if config.proxy_url:
    auth = aiohttp.BasicAuth(login=config.proxy_login, password=config.proxy_password)
    bot = Bot(token=config.token, proxy=config.proxy_url, proxy_auth=auth)
else:
    bot = Bot(token=config.token)
dp = Dispatcher(bot)

#           VARIABLES

userdb = config.db_username
passworddb = config.db_password
namedb = config.db_name
start_message = """Приветствую!"""
# Переменная с валютами, ключи - название валюты
currencies = {"Default": {"Referrals": 5, "Messages": 6, "Bonus": 7, "min_pay": 0, "Active": 0}}
# Переменная с юзерами, ключи - имя юзера
users = {}
pay_requests = {}
allowed_chats = []
banlist = []
about = "Some text about bot"
buttons_lang = [":Russia:Русский", ":England:English"]
buttons_lang = [emojize(x, use_aliases=True) for x in buttons_lang]
menu_buttons_ru = [':white_check_mark:Получить реферальную ссылку',
                   ':moneybag:Мой баланс', 'Настройки',
                   'Статистика', ":family:Мои рефералы",
                   ":back:Назад", ":credit_card:Вывод средств",
                   ":bar_chart:О боте", ":envelope:Связь с администрацией",
                   ":hammer_and_wrench:Сменить язык"]
menu_buttons_ru = [emojize(x,use_aliases=True) for x in menu_buttons_ru]
# Список администраторов
admins = {865146471: {'mode_append': False, 'change_welcome': False, 'mode_append_currencies': 0}}

#                   END VARIABLES


class ReplyKeyboardMarkup(ReplyKeyboardMarkup):
    """Переопределил инициализацию, чтобы задать resize_keyboard=True по умолчанию"""

    def __init__(self, keyboard, resize_keyboard=True, one_time_keyboard=False, selective=False, row_width=3):
        super().__init__(keyboard=keyboard, resize_keyboard=resize_keyboard,
                         one_time_keyboard=one_time_keyboard, selective=selective, row_width=row_width)

    @classmethod
    def from_button(cls, button, resize_keyboard=True, one_time_keyboard=False, selective=False,
                    row_width=3, **kwargs):
        if kwargs.get('update'):
            button = _(button, kwargs['update'])
        return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=button)]], resize_keyboard=resize_keyboard,
                                   one_time_keyboard=one_time_keyboard, selective=selective, row_width=row_width)

    @classmethod
    def from_column(cls, button_column, resize_keyboard=True, one_time_keyboard=False, selective=False, row_width=3,
                    **kwargs):
        if kwargs.get('chat_id'):
            button_column = [_(x, kwargs['chat_id']) for x in button_column]
        column = [[KeyboardButton(text=button)] for button in button_column]
        return ReplyKeyboardMarkup(keyboard=column, resize_keyboard=resize_keyboard, one_time_keyboard=one_time_keyboard,
                                   selective=selective, row_width=row_width)

class InlineKeyboardButton(InlineKeyboardButton):

    def __init__(self,
                 text,
                 chat_id,
                 url=None,
                 callback_data=None,
                 switch_inline_query=None,
                 switch_inline_query_current_chat=None,
                 callback_game=None,
                 pay=None,
                 login_url=None):
        text = _(text, chat_id)
        super().__init__(text=text, url=url, callback_data=callback_data, switch_inline_query=switch_inline_query,
                         switch_inline_query_current_chat=switch_inline_query_current_chat, callback_game=callback_game,
                         pay=pay, login_url=login_url)


def _(text, chat_id, reverse=None):
    if users.get(chat_id):
        if users.get(chat_id).get('Language') == "EN" and chat_id not in admins:
            with open("localize") as file:
                lines = file.readlines()
                for line in lines:
                    if emojize(text, use_aliases=True) in emojize(line, use_aliases=True):
                        if reverse:
                            translated_text = line.split("=")[0]
                        else:
                            translated_text = line.split("=")[1]
                        return emojize(translated_text.strip(), use_aliases=True)
    return emojize(text)


def floatHumanize(str):
    return '{:.10f}'.format(str).rstrip('0').rstrip('.') if str else 0


@dp.message_handler(commands='start')
async def start(message: types.Message):
    """Команда /start"""
    chat_id = message.from_user.id
    username = message.from_user.username

    if chat_id in banlist:
        await message.reply(text="Вы находитесь в черном списке!")
        return 0

    if chat_id not in users:
        users[chat_id] = {'username': username, 'Referrals': 0, 'Messages': 0, 'Inviter': 0,
                               'Language': 'Unknown', 'Payed': 0, 'pay_request_mode': 0}
        if len(message.text.split()) == 2:
            inviter = int(decode_payload(message.text.split()[1]))
            if inviter in users and inviter != chat_id:
                users[chat_id]['Inviter'] = inviter
                text = f"{_('Пользователь', chat_id)} {username} {_('перешёл по вашей ссылке!', chat_id)}"
                await bot.send_message(chat_id=inviter, text=text)
        menu = ReplyKeyboardMarkup.from_column(button_column=buttons_lang)
        await bot.send_message(chat_id=chat_id, text="Выберите язык", reply_markup=menu)
    else:
        menu = ReplyKeyboardMarkup(generateLayout(chat_id))
        await bot.send_message(chat_id=chat_id,text=start_message, reply_markup=menu)
        if users[chat_id].get('Language') == 'EN':
            button = InlineKeyboardButton(text="Join", url="https://t.me/SectorTokenEng")
        else:
            button = InlineKeyboardButton(text="Вступить", url="https://t.me/SectorTokenRussian")
        markup = InlineKeyboardMarkup().insert(button)
        await bot.send_message(chat_id=chat_id, text=_(":speech_balloon:Вступай в наш чат:", chat_id), reply_markup=markup)

async def sendReflink(chat_id):
    """Создаёт deep link и отсылает пользователю"""
    deep_link = await get_start_link(str(chat_id), encode=True)
    await bot.send_message(chat_id=chat_id, text=f"{_('Ваша реферальная ссылка:', chat_id)} {deep_link}")

async def getRefers(chat_id):
    """Возвращает строку рефералов пользователя"""
    refers = ""
    for user in users:
        if users[user]['Inviter'] == chat_id:
            username = users[user]['username']
            if username == "None" or not username:
                username = _("Без имени", chat_id)
            status = await getStatusInChats(userid=user, chats=allowed_chats)
            if not status:
                refers += f"<s>{username}</s>"
            else:
                refers += username
            refers += "\n"
    if refers:
        return refers
    else:
        return _("Нет рефералов", chat_id)
@dp.message_handler()
async def textHandler(message: types.Message):
    """Обработчик сообщений посылаемых кнопками"""
    chat_id = message.from_user.id
    username = message.from_user.username
    buttons_in_settings = ["Администраторы", "Изменить приветствие",
                           "Настроить валюты", "Настройка чатов", "Изменить 'О боте'", "БАН"]

    if chat_id in banlist:
        await bot.send_message(chat_id=chat_id, text="Вы находитесь в черном списке!")
        return 0

    text = message.text
    text = _(text, chat_id, reverse=True)
    if text == menu_buttons_ru[0]:
        await sendReflink(chat_id)
    # Кнопка баланса
    elif text == menu_buttons_ru[1]:
        choice_text = _("Выберите действие", chat_id)
        layout = [menu_buttons_ru[6], menu_buttons_ru[5]]
        inline_markup = [[]]
        for currency in list(currencies.keys())[1:]:
            if currencies[currency]['Active'] == 1:
                balance_info = await getBalanceInfo(chat_id, currency)
                inline_markup[0].append(InlineKeyboardButton(text=currency, callback_data=f"Balance {currency}"))
        if not inline_markup:
            inline_markup[0].append(InlineKeyboardButton(text="Нет валют", chat_id, callback_data='None'))
            balance_info = _("В данный момент, отсутствуют валюты для вывода средств", chat_id)
            layout.__delitem__(0)
        inline_markup = InlineKeyboardMarkup(inline_keyboard=inline_markup)
        markup = ReplyKeyboardMarkup.from_column(button_column=layout, chat_id=chat_id)
        await bot.send_message(chat_id=chat_id, text=balance_info, reply_markup=inline_markup)
        await bot.send_message(chat_id=chat_id, text=choice_text, reply_markup=markup)
    # Кнопка вывода средств
    elif text == menu_buttons_ru[6]:
        if pay_requests.get(chat_id) == 0:
            await bot.send_message(chat_id=chat_id, text=_("Вы уже делали запрос на выплату", chat_id))
        else:
            message_text = _("Выберите валюту", chat_id=chat_id)
            layout = [[]]
            for currency in list(currencies.keys())[1:]:
                if currencies[currency]['Active'] == 1:
                    layout[0].append(InlineKeyboardButton(text=currency, callback_data=f"ChooseCurrency {currency}"))
            markup = InlineKeyboardMarkup(inline_keyboard=layout)
            await bot.send_message(chat_id=chat_id,text=message_text,reply_markup=markup)
            users[chat_id]['pay_request_mode'] = 1
    # Кнопка выбора русского языка
    elif text == buttons_lang[0]:
        users[chat_id]['Language'] = "RU"
        await start(message)
    # Кнопка выбора английского языка
    elif text == buttons_lang[1]:
        users[chat_id]['Language'] = "EN"
        await start(message)
    # Кнопка просмотра личной статистики
    elif text == menu_buttons_ru[4]:
        referal_statistic_message = f"{_('Количество ваших рефералов', chat_id=chat_id)} {users[chat_id]['Referrals']}\n" \
                                    f"{_('Вот их список:', chat_id=chat_id)}\n{getRefers(chat_id)}"
        await bot.send_message(chat_id=chat_id, text=referal_statistic_message, parse_mode='HTML')
    # Кнопка "О боте"
    elif text == menu_buttons_ru[7]:
        global about
        about_bot = emojize(about)
        await bot.send_message(chat_id=chat_id, text=about_bot)
    # Кнопка "Связь с администрацией"
    elif text == menu_buttons_ru[8]:
        markup = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton("Отмена", chat_id, callback_data="CancelOperation")]])
        await bot.send_message(chat_id=chat_id, text=_("Введите ваше сообщение", chat_id), reply_markup=markup)
        users[chat_id]['mode_send_to_admins'] = True
    elif text == menu_buttons_ru[9]:
        if users[chat_id].get('Language') == 'EN':
            users[chat_id]['Language'] = "RU"
        else:
            users[chat_id]['Language'] = "EN"
        await start(message)
    # Кнопка "Назад", возвращает изначальный layout
    elif text == menu_buttons_ru[5]:
        markup = ReplyKeyboardMarkup(generateLayout(chat_id))
        await bot.send_message(chat_id=chat_id, text=_("Вернулись", chat_id=chat_id), reply_markup=markup)
        try:
            users[chat_id]['pay_request_mode'] = 0
            admins[chat_id]["chat_append_mode"] = 0
            admins[chat_id]["mode_send_to_admins"] = True
            admins[chat_id]['change_welcome'] = False
            admins[chat_id]['mode_ban'] = False
        except:
            pass

    elif users[chat_id].get('pay_request_mode'):
        if users[chat_id]['pay_request_mode'].get('currency') and not users[chat_id]['pay_request_mode'].get('sum'):
            text = text.replace(",",".")
            currency = users[chat_id]['pay_request_mode']['currency']
            balance = await getBalance(update, context, currency) \
                            - users[chat_id]['Payed'] * currencies[currency]['Referrals']
            min_pay = floatHumanize(currencies[currency]['min_pay'])
            if float(text) > float("{:.10f}".format(balance)):
                await bot.send_message(chat_id=chat_id,text=_("Сумма превышает доступный баланс", chat_id))
            elif float(text) < float(min_pay if min_pay else 0):
                await bot.send_message(chat_id=chat_id, text=f"{_('Минимальная сумма вывода данной валюты равна', chat_id)}"
                                                             f" {min_pay}")
            else:
                users[chat_id]['pay_request_mode']['sum'] = float(text)
                await bot.send_message(chat_id=chat_id,text=_("Введите номер кошелька", chat_id))

        elif users[chat_id]['pay_request_mode'].get('sum'):
            logger.info(f"User {chat_id} sent pay request")
            message_text = _("Ваш запрос отправлен", chat_id)
            await bot.send_message(chat_id=chat_id, text=message_text)
            currency = users[chat_id]['pay_request_mode']['currency']
            sum = users[chat_id]['pay_request_mode']['sum']
            sum = floatHumanize(sum)
            button = InlineKeyboardButton(text="Выплатить", callback_data=f"Payed {currency} {chat_id} {sum}")
            markup = InlineKeyboardMarkup.from_button(button)
            request_text = f"Запрос на выплату от пользователя " \
                           f"<a href='tg://user?id={chat_id}'>{username}</a>\nСумма: {sum} {currency}\nКошелек: {text}"
            sendtoAdmins(context, text=request_text, markup=markup, parse_mode='HTML')
            pay_requests[chat_id] = 0

    elif users[chat_id].get("mode_send_to_admins"):
        message = f"Пользователь <a href='tg://user?id={chat_id}'>{username}</a> обращается к администраторам:\n{text}"
        sendtoAdmins(context, text=message, parse_mode="HTML")
        context.bot.send_message(chat_id=chat_id, text=_("Ваше сообщение отправлено администраторам", chat_id=chat_id))
        users[chat_id]['mode_send_to_admins'] = False

    # Код ниже работает только для админов
    if chat_id in admins:
        # Переход в настройки
        if text == menu_buttons_ru[2]:
            markup = ReplyKeyboardMarkup([[InlineKeyboardButton(buttons_in_settings[0]), InlineKeyboardButton(buttons_in_settings[5])],
                                          [InlineKeyboardButton(buttons_in_settings[1]),
                                           InlineKeyboardButton(buttons_in_settings[2])],
                                          [InlineKeyboardButton(buttons_in_settings[3]), InlineKeyboardButton(buttons_in_settings[4])],
                                          [InlineKeyboardButton(menu_buttons_ru[5])]])
            context.bot.send_message(chat_id=chat_id, text='Выберите пункт меню', reply_markup=markup)
        # Кнопка запроса статистики всех юзеров
        elif text == menu_buttons_ru[3]:
            sendStatistic(update, context)
        # Кнопка входа в режим добавления админов
        elif text == buttons_in_settings[0]:
            layout = []
            for admin in admins:
                admin_name = users[admin]['username']
                layout.append([InlineKeyboardButton(text=admin_name, callback_data=f"Admin {admin}")])
            layout.append([InlineKeyboardButton(text="Добавить", callback_data="Append Admin")])
            markup = InlineKeyboardMarkup(layout)
            context.bot.send_message(chat_id=chat_id, text="Для удаления нажмите на ник", reply_markup=markup)
        # Кнопка входа в режим изменения приветствия
        elif text == buttons_in_settings[1]:
            admins[chat_id]['change_welcome'] = True
            markup = ReplyKeyboardMarkup.from_button(menu_buttons_ru[5], chat_id=chat_id=update)
            context.bot.send_message(chat_id=chat_id, text="Напишите текст приветствия", reply_markup=markup)
        # Кнопка ввода валют
        elif text == buttons_in_settings[2]:
            current_currencies = "Текущие настройки:\n" \
                                 "<Название> <Стоимость реферала> <Стоимость сообщения> <Бонус> <Минимальная выплата> <0-выкл, 1 - вкл>"
            layout = []
            for index, currency in enumerate(list(currencies.keys())):
                layout.append([InlineKeyboardButton(text=currency, callback_data=currency)])
                for param in currencies[currency]:
                    value = currencies[currency][param]
                    if type(value) == float:
                        value = "{:.10f}".format(value).rstrip("0").rstrip(".") if value else 0
                    callback = f"{param} {currency}"
                    layout[index].append(InlineKeyboardButton(text=f"{value}",callback_data=callback))
            layout.append([InlineKeyboardButton(text="Добавить",callback_data="Append currency")])
            context.bot.send_message(chat_id=chat_id,text=current_currencies, reply_markup=InlineKeyboardMarkup(layout))

        elif text == buttons_in_settings[3]:
            markup = getAllowedChats()
            context.bot.send_message(chat_id=chat_id, text="Для удаления чата нажмите на него", reply_markup=markup)

        elif text == buttons_in_settings[4]:
            admins[chat_id]['mode_edit_about'] = True
            markup = InlineKeyboardMarkup.from_button(InlineKeyboardButton(menu_buttons_ru[5],
                                                                           callback_data="CancelOperation"))
            context.bot.send_message(chat_id=chat_id, text="Введите текст", reply_markup=markup)

        elif text == buttons_in_settings[5]:
            admins[chat_id]['mode_ban'] = True
            context.bot.send_message(chat_id=chat_id, text="Введите CHAT ID пользователя, которого нужно удалить")

        elif admins[chat_id].get('mode_ban'):
            user_id = int(text)
            if user_id not in users:
                context.bot.send_message(chat_id=chat_id, text="Данный пользователь не найден")
            else:
                username = users[user_id]['username'] if users[user_id]['username'] else "None"
                markup = InlineKeyboardMarkup.from_button(
                    InlineKeyboardButton(text="Да, бан!", callback_data=f"BAN {user_id}"))
                context.bot.send_message(chat_id=chat_id, text=f"Вы действительно хотите забанить пользователя"
                                                               f" с ником {username}?", reply_markup=markup)

        elif admins[chat_id].get('mode_edit_about'):
            about = text
            context.bot.send_message(chat_id=chat_id, text="Вы изменили информацию о боте!")
            admins[chat_id]['mode_edit_about'] = False

        elif admins[chat_id]['mode_append']:
            addtoAdmin(update, context, text)
            admins[chat_id]['mode_append'] = False

        # Меняет приветствие на присланный текст
        elif text and admins[chat_id].get('change_welcome'):
            logger.info(f"Admin {chat_id} change welcome")
            start_message = update.message.text
            context.bot.send_message(chat_id=chat_id, text="Вы изменили приветствие")
            admins[chat_id]['change_welcome'] = False

        elif admins[chat_id].get('mode_append_currencies') == 1:
            try:
                passed_params = text.split()
                currencies[passed_params[0]] = {}
                for index, param in enumerate(list(currencies['Default'].keys())):
                    value = passed_params[index+1].replace(",",".")
                    currencies[passed_params[0]][param] = float(value) if param != "Active" else int(value)
                context.bot.send_message(chat_id=chat_id,text="Новая валюта добавлена!")
                admins[chat_id]['mode_append_currencies'] = 0
                logger.info(f"Admin {chat_id} has add new currency")
            except:
                context.bot.send_message(chat_id=chat_id,text="Ошибка при вводе параметров!")

        elif admins[chat_id].get('mode_append_chat') == 1:
            admins[chat_id]['mode_append_chat'] = 0
            allowed_chats.append(text)
            markup = getAllowedChats()
            context.bot.send_message(chat_id=chat_id,text=f"Чат {text} успешно добавлен", reply_markup=markup)

# def getAllowedChats(:
#     markup = []
#     for chat in allowed_chats:
#         markup.append(InlineKeyboardButton(text=chat, callback_data=f"Chat {chat}"))
#     markup.append(InlineKeyboardButton(text="Добавить", callback_data="ChatAppend"))
#     markup = InlineKeyboardMarkup.from_column(markup)
#     return markup

async def getBalance(chat_id, currency):
    balance = currencies[currency]['Referrals'] * users[chat_id]['Referrals'] \
              + currencies[currency]['Messages'] * users[chat_id]['Messages'] \
              + currencies[currency]['Bonus']
    return balance


async def getBalanceInfo(chat_id, currency):
    """Считает и возвращает данные по балансу"""
    already_payed = currencies[currency]['Referrals'] * users[chat_id]['Payed']
    already_payed = floatHumanize(already_payed)
    balance = getBalance(chat_id, currency) - float(already_payed)
    balance = floatHumanize(balance)
    start_bonus = currencies[currency]['Bonus']
    start_bonus = floatHumanize(start_bonus)
    balance_information = emojize(f"""
    {_(':dollar:Баланс:', chat_id)} {balance} {currency}
    \n{_(':arrow_up:Стартовый бонус:', chat_id)} {start_bonus} {currency}
    \n{_(':loudspeaker:Вы пригласили:', chat_id)} {users[chat_id]['Referrals']} {_('человека', chat_id=chat_id)}
    \n{_(':email:Написано:', chat_id)} {users[chat_id]['Messages']} {_('сообщений', chat_id)}
    \n{_(':money_with_wings:Уже выплачено:', chat_id)} {already_payed} {currency}
    """, use_aliases=True)
    return balance_information

def sendStatistic( update, context):
    """Админская функция просмотра статистики всех пользователей"""
    chat_id = update.effective_chat.id
    statistic_message = """
    <head><meta charset='utf-8'></head>
    <table class="sortable"><tr><th>№</th><th>Имя пользователя</th><th>Chat ID</th>
    <th>Рефералы</th><th>Сообщения</th><th>Пригласитель</th></tr>"""
    i=0
    for user in users:
        i += 1
        refers = users[user]['Referrals']
        messages = users[user]['Messages']
        inviter = users[user]['Inviter']
        inviter_name = ""
        if inviter and inviter != 0:
            inviter_name = f" / {users[inviter]['username']}"
        username = users[user]['username']
        statistic_message += f"<tr><td>{i}</td><td>{username}</td><td><a name='{user}'>{user}</a></td>" \
                             f"<td>{refers}</td>" \
                             f"<td>{messages}</td><td><a href='#{inviter}'>{inviter}{inviter_name}</a></td><tr>"
    statistic_message += "</table>"
    with open("stat.html","w") as f:
        f.write(statistic_message)
        f.write("<script>")
        with open("sorttable.js","r", encoding='utf-8') as js:
            f.write(js.read())
        f.write("</script>")
    with open("stat.html","rb") as f:
        context.bot.send_document(chat_id=chat_id, document=f)

def deletefromAdmin( update, context, userid):
    """Удаляет из админов"""
    try:
        username = users[userid]['username']
        admins.__delitem__(userid)
        context.bot.send_message(chat_id=userid,
                                 text=f"Админ {update.effective_chat.username} удалил вас из администраторов")
        context.bot.send_message(chat_id=update.effective_chat.id, text=f"Вы удалили юзера {username} из админов")
        logger.info(f"Admin {update.effective_chat.username} delete from admin user {username}")
    except KeyError:
        context.bot.send_message(chat_id=update.effective_chat.id, text=f"Пользователь не найден")
        logger.error("Error during delete admin")

def addtoAdmin( update, context, username):
    """Добавляет юзера в список администраторов"""
    userid = None
    for id in users:
        if users[id]['username'] == username:
            userid = id
            break
    try:
        username = users[userid]['username']
        admins[userid] = {'mode_append': False}
        context.bot.send_message(chat_id=userid,
                                 text=f"Админ {update.effective_chat.username} сделал вас админом")
        context.bot.send_message(chat_id=update.effective_chat.id, text=f"Вы сделали юзера {username} админом")
        logger.info(f"Admin {update.effective_chat.username} make admin user {username}")
    except KeyError:
        context.bot.send_message(chat_id=update.effective_chat.id, text=f"Пользователь {username} не найден")

def generateLayout(chat_id):
    """Генерирует стартовый layout, исходя из того админ или нет"""
    if chat_id in admins:
        layout = [[KeyboardButton(text=menu_buttons_ru[2])],
                  [KeyboardButton(text=menu_buttons_ru[3])]]
    else:
        layout = [[KeyboardButton(text=menu_buttons_ru[0]),
                   KeyboardButton(text=menu_buttons_ru[4])],
                  [KeyboardButton(text=menu_buttons_ru[1]),
                   KeyboardButton(text=menu_buttons_ru[7])],
                  [KeyboardButton(text=menu_buttons_ru[8]),
                   KeyboardButton(text=menu_buttons_ru[9])]]
    return layout

def inlineHandler(update, context):
    chat_id = update.effective_chat.id
    username = users[chat_id]['username']
    query = update.callback_query
    data = query.data
    if data == "Append currency":
        append_currency_text = """
        Введите новую валюту в следующем формате:
        \n<Название> <Стоимость реферала> <Стоимость сообщения> <Бонус> <Минимальная выплата> <0-выкл, 1 - вкл>"""
        context.bot.send_message(chat_id=chat_id,text=append_currency_text)
        admins[chat_id]['mode_append_currencies'] = 1

    elif "CancelOperation" in data:
        context.bot.send_message(chat_id=chat_id, text=_("Операция отменена", chat_id=chat_id))
        try:
            users[chat_id]["mode_send_to_admins"] = False
            admins[chat_id]['mode_edit_about'] = False
        except:
            pass

    elif data in currencies and data != "Default":
        currencies.__delitem__(data)
        context.bot.send_message(chat_id=chat_id,text=f"Валюта {data} удалена")

    elif "Active" in data:
        currency = data.split()[1]
        current_state = int(currencies[currency]['Active'])
        current_state ^= 1
        currencies[currency]['Active'] = current_state
        context.bot.send_message(chat_id=chat_id,text=f"Состояние валюты {currency} переключено")

    elif "Balance" in data:
        currency = data.split()[1]
        query.edit_message_text(text=getBalanceInfo(update, context, currency))
        inline_markup = []
        for currency in list(currencies.keys())[1:]:
            if currencies[currency]['Active'] == 1:
                inline_markup.append(InlineKeyboardButton(text=currency, callback_data=f"Balance {currency}"))
        if not inline_markup:
            inline_markup.append(InlineKeyboardButton(text=_("Нет валют", chat_id), callback_data='None'))
        inline_markup = InlineKeyboardMarkup.from_row(inline_markup)
        query.edit_message_reply_markup(reply_markup=inline_markup)

    # Button "Payed"
    elif "Payed" in data:
        currency = data.split()[1]
        user_chatid = int(data.split()[2])
        sum_payed = data.split()[3]
        if pay_requests[user_chatid] == 0:
            users[user_chatid]['Payed'] += float(sum_payed) / currencies[currency]['Referrals']
            context.bot.send_message(chat_id=user_chatid,text=f"{_('Вам выплачено',user=user_chatid)} "
                                                              f"{sum_payed} {currency}")
            pay_requests[user_chatid] = username
        else:
            query.answer(text=f"Выплата уже была произведена админом {pay_requests[user_chatid]}",show_alert=True)

    # Delete from chat's monitoring
    elif "Chat" == data.split()[0]:
        chat = data.split()[1]
        allowed_chats = [x for x in allowed_chats if x != chat]
        query.answer(text=f"Чат с ID: {chat} удален", show_alert=True)
        markup = getAllowedChats()
        query.edit_message_reply_markup(reply_markup=markup)

    # Append chat to monitoring's chats
    elif "ChatAppend" in data:
        admins[chat_id]['mode_append_chat'] = 1
        context.bot.send_message(chat_id=chat_id,text="Введите ID чата")

    # Append to admins
    elif "Append Admin" == data:
        context.bot.send_message(chat_id=chat_id,text="Введите имя пользователя")
        admins[chat_id]['mode_append'] = True

    # Delete from admin
    elif "Admin" in data:
        deladmin = data.split()[1]
        deletefromAdmin(update, context, int(deladmin))

    # Choose currency in balance menu
    elif "ChooseCurrency" in data:
        currency = data.split()[1]
        users[chat_id]['pay_request_mode'] = {'currency': currency}
        balance = getBalance(update, context, currency) - \
                  users[chat_id]['Payed'] * currencies[currency]['Referrals']
        if balance <= 0:
            message_text = f"{_('В данный момент у вас недостаточно средств для выплаты в', chat_id)} {currency}"
            users[chat_id]['pay_request_mode'] = 0
        else:
            message_text = f"{_('Ваш доступный баланс в', chat_id)} {currency}: " \
                           f"{'{:.10f}'.format(balance).rstrip('0').rstrip('.') if balance else 0}" \
                           f"\n{_('Введите сумму', chat_id=chat_id)}"
        context.bot.send_message(chat_id=chat_id, text=message_text)

    elif "BAN" in data:
        user_id = int(data.split()[1])
        users.__delitem__(user_id)
        for id in users:
            if users[id]['Inviter'] == user_id:
                users[id]['Inviter'] = 0
        con = pymysql.connect('localhost', userdb, passworddb, namedb)
        with con:
            query_delete = f"DELETE from users where chat_id={user_id};"
            curs = con.cursor()
            curs.execute(query_delete)
        banlist.append(user_id)
        context.bot.send_message(chat_id=chat_id, text=f"Вы забанили пользователя с Chat ID {user_id}")
        logger.info(f"Админ {chat_id} забанил {user_id}")

    query.answer()

def sendtoAdmins( context, parse_mode=None, **kwargs):
    """Отправляет всем админам сообщение"""
    try:
        for chat_id in admins:
            if kwargs.get('markup'):
                context.bot.send_message(chat_id=chat_id,text=kwargs['text'], reply_markup=kwargs['markup'],
                                         parse_mode=parse_mode)
            else:
                context.bot.send_message(chat_id=chat_id,text=kwargs['text'], parse_mode=parse_mode)
    except Exception as e:
        logger.error(e)

def getRefCount( chat_id, bot=None, context=None):
    refcount = 0
    for id in users:
        status = getStatusInChats(bot=bot, context=context, userid=id, chats=allowed_chats)
        if users[id]['Inviter'] == chat_id and status:
            refcount += 1
    return refcount


# def saveParams(:
#     """Сохраняет настройки (текст приветствия, валюты, бонусы) в файл"""
#     logger.info("Save params to file")
#     with shelve.open('params.db') as params:
#         params['start_message'] = start_message
#         params['currencies'] = currencies
#         params['allowed_chats'] = allowed_chats
#         params['about'] = about
#         params['banlist'] = banlist
#
# def loadParams(:
#     """Загружает настройки из файла"""
#     logger.info("Loading params from file")
#     with shelve.open('params.db') as params:
#         try:
#             start_message = params['start_message']
#             currencies = params['currencies']
#             allowed_chats = params['allowed_chats']
#             about = params['about']
#             banlist = params['banlist']
#         except Exception as e:
#             logger.error(f"Ошибка при загрузке параметров {e}")

def saveToDB( context):
    """Сохраняет или обновляет записи в БД"""
    saveParams()
    logger.info("Save and sync database...")
    con = pymysql.connect('localhost', userdb, passworddb, namedb)
    with con:
        curs = con.cursor()
        for chat_id in users:
            username = users[chat_id]['username']
            refs = users[chat_id]['Referrals']
            messages = users[chat_id]['Messages']
            inviter = users[chat_id]['Inviter']
            lang = users[chat_id]['Language']
            payed = users[chat_id]['Payed']
            if chat_id in admins:
                isadmin = 1
            else:
                isadmin = 0
            query_find = f"SELECT * from users where chat_id={chat_id}"
            curs.execute(query_find)
            if curs.fetchall():
                query_update = f"UPDATE users set username='{username}',Referrals={refs},Messages={messages}," \
                               f"isadmin={isadmin},payed={payed} where chat_id={chat_id};"
                curs.execute(query_update)
            else:
                query_save = f"INSERT INTO users VALUES('{username}',{chat_id},{refs}," \
                             f"{messages},{inviter},'{lang}',{isadmin},{payed});"
                curs.execute(query_save)

def loadfromDB( bot):
    """Загружает все параметры из БД в переменные"""
    loadParams()
    logger.info("Loading from DB")
    con = pymysql.connect('localhost', userdb, passworddb, namedb)
    with con:
        curs = con.cursor()
        query_select = "SELECT * from users;"
        curs.execute(query_select)
        rows = curs.fetchall()
        for row in rows:
            chat_id = row[1]
            users[chat_id] = {}
            users[chat_id]['username'] = row[0]
            users[chat_id]['Messages'] = row[3]
            users[chat_id]['Inviter'] = row[4]
            users[chat_id]['Referrals'] = row[2]
            users[chat_id]['Language'] = row[5]
            users[chat_id]['Payed'] = row[7]
            users[chat_id]['pay_request_mode'] = 0
            if row[6] == 1:
                admins[chat_id] = {'mode_append': False, 'change_welcome': False}
        # for id in list(users):
        #     inviter = users[id]['Inviter']
        #     if inviter != 0:
        #         if inviter not in users:
        #             users.__delitem__(id)
        #             con = pymysql.connect('localhost', userdb, passworddb, namedb)
        #             with con:
        #                 query_delete = f"DELETE from users where chat_id={id};"
        #                 curs = con.cursor()
        #                 curs.execute(query_delete)

def messageGroup( update, context):
    """Обработчик текстовых сообщений в чате"""
    if not update.message:
        return 0
    userid = update.message.from_user.id
    chatmessage_name = update.message.chat.username
    if chatmessage_name in allowed_chats:
        try:
            users[userid]['Messages'] += 1
        except KeyError:
            pass

def getStatusInChats( userid, chats, bot=None, context=None):
    for chat in chats:
        try:
            if bot:
                status = bot.get_chat_member(user_id=userid, chat_id=f"@{chat}").status
            elif context:
                status = context.bot.get_chat_member(user_id=userid, chat_id=f"@{chat}").status
        except TelegramError:
            status = 'Not found'
        finally:
            if status in ['creator', 'administrator', 'member']:
                return True
    return False

def join_or_left_Group( update, context):
    chatmessage_name = update.message.chat.username
    if chatmessage_name in allowed_chats:
        new_members = update.message.new_chat_members
        left_member = update.message.left_chat_member
        for member in new_members:
            userid = member.id
            if userid in users:
                if not getStatusInChats(context=context, userid=userid,
                                             chats=[x for x in allowed_chats if x != chatmessage_name]):
                    inviter = users[userid]['Inviter']
                    if inviter != 0:
                        users[inviter]['Referrals'] += 1
        if left_member:
            userid = left_member.id
            if userid in users:
                if not getStatusInChats(context=context, userid=userid, chats=allowed_chats):
                    inviter = users[userid]['Inviter']
                    if inviter != 0:
                        users[inviter]['Referrals'] -= 1

def unban( update, context):
    chat_id = update.effective_chat.id
    if chat_id in admins:
        try:
            banlist = [x for x in banlist if x != int(context.args[0])]
            context.bot.send_message(chat_id=chat_id, text="Разбанен")
        except:
            context.bot.send_message(chat_id=chat_id, text="Ошибка")


if __name__ == "__main__":
    # Аргументы, логин и пароль от базы данных
    # referral.loadfromDB(bot)
    # Периодическая синхронизация с базой данных
    # job = updater.job_queue
    # job.run_repeating(callback=referral.saveToDB, interval=1800)

    executor.start_polling(dp)

    #dp.add_handler(CommandHandler('unban', callback=referral.unban, pass_args=True))
    #dp.add_handler(CommandHandler(filters=~Filters.group,command='start', callback=referral.start))
    # # Отлавливает сообщения в чате, в который добавлен бот, учитывает только текст
    #dp.add_handler(MessageHandler((Filters.group & Filters.text), referral.messageGroup))
    #
    #dp.add_handler(MessageHandler(Filters.group, referral.join_or_left_Group))
    # # Отлавливает посылаемый текст, при нажатии кнопок
    #dp.add_handler(MessageHandler((Filters.text & (~Filters.group)), referral.onClickMenu))
    # # Обработчик InlineKeyboard
    #dp.add_handler(CallbackQueryHandler(callback=referral.inlineHandler))
    # # Опрос бота, таймаут для того, чтобы бот периодически не ломался при плохом соединении
    # logger.info("Start!")
    # # При любом завершении программы, сохраняем всё в БД
    # atexit.register(referral.saveToDB, context=bot)