from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import InlineKeyboardMarkup, ContentTypes
from aiogram.types import InlineKeyboardButton, ReplyKeyboardMarkup, CallbackQuery, KeyboardButton
from aiogram.utils.deep_linking import get_start_link, decode_payload
from aiogram.utils.exceptions import TelegramAPIError
from aiogram.types.chat import ChatType
import asyncio
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

#-----------VARIABLES---------------------------------

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


#-------------------END VARIABLES --------------------------------------------


class ReplyKeyboardMarkup(ReplyKeyboardMarkup):
    """Переопределил инициализацию, чтобы задать resize_keyboard=True по умолчанию"""

    def __init__(self, keyboard, resize_keyboard=True, one_time_keyboard=False, selective=False, row_width=3):
        super().__init__(keyboard=keyboard, resize_keyboard=resize_keyboard,
                         one_time_keyboard=one_time_keyboard, selective=selective, row_width=row_width)


class KeyboardButton(KeyboardButton):
    """Переопределяю для перевода текста кнопки"""
    def __init__(self, text, chat_id=None,
                 request_contact=None,
                 request_location=None,
                 request_poll=None):
        text = _(text, chat_id)
        super().__init__(text=text, request_contact=request_contact,
                         request_location=request_location, request_poll=request_poll)


class InlineKeyboardButton(InlineKeyboardButton):
    """Переопределяю инициализацию, чтобы перевести текст кнопки"""
    def __init__(self,
                 text,
                 chat_id=None,
                 url=None,
                 callback_data=None,
                 switch_inline_query=None,
                 switch_inline_query_current_chat=None,
                 callback_game=None,
                 pay=None,
                 login_url=None,
                 **kwargs):
        text = _(text, chat_id)
        super().__init__(text=text, url=url, callback_data=callback_data, switch_inline_query=switch_inline_query,
                         switch_inline_query_current_chat=switch_inline_query_current_chat, callback_game=callback_game,
                         pay=pay, login_url=login_url, **kwargs)


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




@dp.message_handler(lambda message: ChatType.is_private(message), commands='start')
async def start(message=types.Message):
    """Команда /start"""
    global users
    chat_id = message.from_user.id
    username = message.from_user.username

    if chat_id in banlist:
        await message.reply(text="Вы находитесь в черном списке!")
        return 0

    if chat_id not in users:
        users[chat_id] = {'Username': username, 'Referrals': 0, 'Messages': 0, 'Inviter': 0,
                               'Language': 'RU', 'Payed': 0, 'pay_request_mode': 0}
        if len(message.text.split()) == 2:
            inviter = int(decode_payload(message.text.split()[1]))
            if inviter in users and inviter != chat_id:
                users[chat_id]['Inviter'] = inviter
                text = f"{_('Пользователь', chat_id)} {username} {_('перешёл по вашей ссылке!', chat_id)}"
                await bot.send_message(chat_id=inviter, text=text)
        menu = ReplyKeyboardMarkup([[KeyboardButton(button)] for button in buttons_lang])
        await bot.send_message(chat_id=chat_id, text="Выберите язык", reply_markup=menu)
    else:
        menu = ReplyKeyboardMarkup(await generateLayout(chat_id))
        await bot.send_message(chat_id=chat_id,text=start_message, reply_markup=menu)
        if users[chat_id].get('Language') == 'EN':
            button = InlineKeyboardButton(text="Join", url="https://t.me/SectorTokenEng")
        else:
            button = InlineKeyboardButton(text="Вступить", url="https://t.me/SectorTokenRussian")
        markup = InlineKeyboardMarkup(inline_keyboard=[[button]])
        await bot.send_message(chat_id=chat_id, text=_(":speech_balloon:Вступай в наш чат:", chat_id), reply_markup=markup)

content_types = ContentTypes.NEW_CHAT_MEMBERS | ContentTypes.LEFT_CHAT_MEMBER
@dp.message_handler(lambda message: ChatType.is_group_or_super_group(message), content_types=content_types)
async def join_or_left_Group(message=types.Message):
    chatmessage_name = message.chat.username
    if chatmessage_name in allowed_chats:
        new_members = message.new_chat_members
        left_member = message.left_chat_member
        for member in new_members:
            userid = member.id
            if userid in users:
                if not await getStatusInChats(userid=userid, chats=[x for x in allowed_chats if x != chatmessage_name]):
                    inviter = users[userid]['Inviter']
                    if inviter != 0:
                        users[inviter]['Referrals'] += 1
        if left_member:
            userid = left_member.id
            if userid in users:
                if not await getStatusInChats(userid=userid, chats=allowed_chats):
                    inviter = users[userid]['Inviter']
                    if inviter != 0:
                        users[inviter]['Referrals'] -= 1


async def sendReflink(chat_id):
    """Создаёт deep link и отсылает пользователю"""
    deep_link = await get_start_link(str(chat_id), encode=True)
    await bot.send_message(chat_id=chat_id, text=f"{_('Ваша реферальная ссылка:', chat_id)} {deep_link}")

async def getRefers(chat_id):
    """Возвращает строку рефералов пользователя"""
    refers = ""
    for user in users:
        if users[user]['Inviter'] == chat_id:
            users[chat_id]['Referrals'] = 0
            username = users[user]['Username']
            if username == "None" or not username:
                username = _("Без имени", chat_id)
            status = await getStatusInChats(userid=user, chats=allowed_chats)
            if not status:
                refers += f"<s>{username}</s>"
            else:
                users[chat_id]['Referrals'] += 1
                refers += username
            refers += "\n"
    if refers:
        return refers
    else:
        return _("Нет рефералов", chat_id)


@dp.message_handler(lambda message: not message.is_command() and ChatType.is_private(message))
async def textHandler(message=types.Message):
    """Обработчик сообщений посылаемых кнопками"""
    global users, admins, start_message, currencies, pay_requests, allowed_chats, banlist, about
    chat_id = message.from_user.id

    if not users.get(chat_id):
        await start(message)
        return 0

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
            inline_markup[0].append(InlineKeyboardButton(text="Нет валют", chat_id=chat_id, callback_data='None'))
            balance_info = _("В данный момент, отсутствуют валюты для вывода средств", chat_id)
            layout.__delitem__(0)
        inline_markup = InlineKeyboardMarkup(inline_keyboard=inline_markup)
        markup = ReplyKeyboardMarkup([[KeyboardButton(but,chat_id=chat_id)] for but in layout])
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
        ref_list = await getRefers(chat_id)
        referal_statistic_message = f"{_('Количество ваших рефералов', chat_id=chat_id)} {users[chat_id]['Referrals']}\n" \
                                    f"{_('Вот их список:', chat_id=chat_id)}\n{ref_list}"
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
        markup = ReplyKeyboardMarkup(await generateLayout(chat_id))
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
            balance = await getBalance(chat_id, currency) \
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
            markup = InlineKeyboardMarkup([[button]])
            request_text = f"Запрос на выплату от пользователя " \
                           f"<a href='tg://user?id={chat_id}'>{username}</a>\nСумма: {sum} {currency}\nКошелек: {text}"
            await sendtoAdmins(text=request_text, reply_markup=markup, parse_mode='HTML')
            pay_requests[chat_id] = 0

    elif users[chat_id].get("mode_send_to_admins"):
        message = f"Пользователь <a href='tg://user?id={chat_id}'>{username}</a> обращается к администраторам:\n{text}"
        await sendtoAdmins(text=message, parse_mode="HTML")
        await bot.send_message(chat_id=chat_id, text=_("Ваше сообщение отправлено администраторам", chat_id=chat_id))
        users[chat_id]['mode_send_to_admins'] = False

    # Код ниже работает только для админов
    if chat_id in admins:
        # Переход в настройки
        if text == menu_buttons_ru[2]:
            markup = ReplyKeyboardMarkup([[KeyboardButton(buttons_in_settings[0]), KeyboardButton(buttons_in_settings[5])],
                                          [KeyboardButton(buttons_in_settings[1]),
                                           KeyboardButton(buttons_in_settings[2])],
                                          [KeyboardButton(buttons_in_settings[3]), KeyboardButton(buttons_in_settings[4])],
                                          [KeyboardButton(menu_buttons_ru[5])]])
            await bot.send_message(chat_id=chat_id, text='Выберите пункт меню', reply_markup=markup)
        # Кнопка запроса статистики всех юзеров
        elif text == menu_buttons_ru[3]:
            await sendStatistic(chat_id)
        # Кнопка входа в режим добавления админов
        elif text == buttons_in_settings[0]:
            layout = []
            for admin in admins:
                admin_name = users[admin]['Username']
                layout.append([InlineKeyboardButton(text=admin_name, callback_data=f"Admin {admin}")])
            layout.append([InlineKeyboardButton(text="Добавить", callback_data="Append Admin")])
            markup = InlineKeyboardMarkup(inline_keyboard=layout)
            await bot.send_message(chat_id=chat_id, text="Для удаления нажмите на ник", reply_markup=markup)
        # Кнопка входа в режим изменения приветствия
        elif text == buttons_in_settings[1]:
            admins[chat_id]['change_welcome'] = True
            markup = ReplyKeyboardMarkup([[menu_buttons_ru[5]]])
            await bot.send_message(chat_id=chat_id, text="Напишите текст приветствия", reply_markup=markup)
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
                        value = floatHumanize(value)
                    callback = f"{param} {currency}"
                    layout[index].append(InlineKeyboardButton(text=f"{value}",callback_data=callback))
            layout.append([InlineKeyboardButton(text="Добавить",callback_data="Append currency")])
            markup = InlineKeyboardMarkup(inline_keyboard=layout)
            await bot.send_message(chat_id=chat_id,text=current_currencies, reply_markup=markup)

        elif text == buttons_in_settings[3]:
            markup = await getAllowedChats()
            await bot.send_message(chat_id=chat_id, text="Для удаления чата нажмите на него", reply_markup=markup)
        # Кнопка "Изменить о боте"
        elif text == buttons_in_settings[4]:
            admins[chat_id]['mode_edit_about'] = True
            button = [[InlineKeyboardButton(menu_buttons_ru[5], callback_data="CancelOperation")]]
            markup = InlineKeyboardMarkup(inline_keyboard=button)
            await bot.send_message(chat_id=chat_id, text="Введите текст", reply_markup=markup)

        elif text == buttons_in_settings[5]:
            admins[chat_id]['mode_ban'] = True
            await bot.send_message(chat_id=chat_id, text="Введите CHAT ID пользователя, которого нужно удалить")

        elif admins[chat_id].get('mode_ban'):
            user_id = int(text)
            if user_id not in users:
                await bot.send_message(chat_id=chat_id, text="Данный пользователь не найден")
            else:
                username = users[user_id]['Username'] if users[user_id]['Username'] else "None"
                markup = InlineKeyboardMarkup([[InlineKeyboardButton(text="Да, бан!", callback_data=f"BAN {user_id}")]])
                await bot.send_message(chat_id=chat_id, text=f"Вы действительно хотите забанить пользователя"
                                                               f" с ником {username}?", reply_markup=markup)

        elif admins[chat_id].get('mode_edit_about'):
            about = text
            await bot.send_message(chat_id=chat_id, text="Вы изменили информацию о боте!")
            admins[chat_id]['mode_edit_about'] = False

        elif admins[chat_id]['mode_append']:
            await addtoAdmin(chat_id, text)
            admins[chat_id]['mode_append'] = False

        # Меняет приветствие на присланный текст
        elif text and admins[chat_id].get('change_welcome'):
            logger.info(f"Admin {chat_id} change welcome")
            start_message = message.text
            await bot.send_message(chat_id=chat_id, text="Вы изменили приветствие")
            admins[chat_id]['change_welcome'] = False

        elif admins[chat_id].get('mode_append_currencies') == 1:
            try:
                passed_params = text.split()
                currencies[passed_params[0]] = {}
                for index, param in enumerate(list(currencies['Default'].keys())):
                    value = passed_params[index+1].replace(",",".")
                    currencies[passed_params[0]][param] = float(value) if param != "Active" else int(value)
                await bot.send_message(chat_id=chat_id,text="Новая валюта добавлена!")
                admins[chat_id]['mode_append_currencies'] = 0
                logger.info(f"Admin {chat_id} has add new currency")
            except:
                await bot.send_message(chat_id=chat_id,text="Ошибка при вводе параметров!")

        elif admins[chat_id].get('mode_append_chat') == 1:
            admins[chat_id]['mode_append_chat'] = 0
            allowed_chats.append(text)
            markup = await getAllowedChats()
            await bot.send_message(chat_id=chat_id,text=f"Чат {text} успешно добавлен", reply_markup=markup)

async def getAllowedChats():
    markup = []
    for chat in allowed_chats:
        markup.append(InlineKeyboardButton(text=chat, callback_data=f"Chat {chat}"))
    markup.append(InlineKeyboardButton(text="Добавить", callback_data="ChatAppend"))
    markup = InlineKeyboardMarkup(inline_keyboard=[[button] for button in markup])
    return markup

async def getBalance(chat_id, currency):
    balance = currencies[currency]['Referrals'] * users[chat_id]['Referrals'] \
              + currencies[currency]['Messages'] * users[chat_id]['Messages'] \
              + currencies[currency]['Bonus']
    return balance


async def getBalanceInfo(chat_id, currency):
    """Считает и возвращает данные по балансу"""
    already_payed = currencies[currency]['Referrals'] * users[chat_id]['Payed']
    already_payed = floatHumanize(already_payed)
    balance = await getBalance(chat_id, currency) - float(already_payed)
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

async def sendStatistic(chat_id):
    """Админская функция просмотра статистики всех пользователей"""
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
            inviter_name = f" / {users[inviter]['Username']}"
        username = users[user]['Username']
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
        await bot.send_document(chat_id=chat_id, document=f)

async def deletefromAdmin(chat_id, userid):
    """Удаляет из админов"""
    global admins
    admin_name = users[chat_id]['Username']
    try:
        username = users[userid]['Username']
        admins.__delitem__(userid)
        await bot.send_message(chat_id=userid,
                                 text=f"Админ {admin_name} удалил вас из администраторов")
        await bot.send_message(chat_id=chat_id, text=f"Вы удалили юзера {username} из админов")
        logger.info(f"Admin {chat_id} delete from admin user {username}")
    except KeyError:
        await bot.send_message(chat_id=chat_id, text=f"Пользователь не найден")
        logger.error("Error during delete admin")

async def addtoAdmin(chat_id, username):
    """Добавляет юзера в список администраторов"""
    global admins
    admin_name = users[chat_id]['Username']
    userid = None
    for id in users:
        if users[id]['Username'] == username:
            userid = id
            break
    try:
        username = users[userid]['Username']
        admins[userid] = {'mode_append': False}
        await bot.send_message(chat_id=userid, text=f"Админ {admin_name} сделал вас админом")
        await bot.send_message(chat_id=chat_id, text=f"Вы сделали юзера {username} админом")
        logger.info(f"Admin {chat_id} make admin user {username}")
    except KeyError:
        await bot.send_message(chat_id=chat_id, text=f"Пользователь {username} не найден")

async def generateLayout(chat_id):
    """Генерирует стартовый layout, исходя из того админ или нет"""
    if chat_id in admins:
        layout = [[KeyboardButton(text=menu_buttons_ru[2])],
                  [KeyboardButton(text=menu_buttons_ru[3])]]
    else:
        layout = [[KeyboardButton(text=menu_buttons_ru[0], chat_id=chat_id),
                   KeyboardButton(text=menu_buttons_ru[4], chat_id=chat_id)],
                  [KeyboardButton(text=menu_buttons_ru[1], chat_id=chat_id),
                   KeyboardButton(text=menu_buttons_ru[7], chat_id=chat_id)],
                  [KeyboardButton(text=menu_buttons_ru[8], chat_id=chat_id),
                   KeyboardButton(text=menu_buttons_ru[9], chat_id=chat_id)]]
    return layout

@dp.callback_query_handler(lambda query: True)
async def callbackHandler(query=types.CallbackQuery):
    global users, admins, start_message, currencies, pay_requests, allowed_chats, banlist, about
    chat_id = query.from_user.id

    if not users.get(chat_id):
        await query.answer("Please type /start", show_alert=True)
        return 0

    username = users[chat_id]['Username']
    data = query.data
    if data == "Append currency":
        append_currency_text = """
        Введите новую валюту в следующем формате:
        \n<Название> <Стоимость реферала> <Стоимость сообщения> <Бонус> <Минимальная выплата> <0-выкл, 1 - вкл>"""
        await bot.send_message(chat_id=chat_id,text=append_currency_text)
        admins[chat_id]['mode_append_currencies'] = 1

    elif "CancelOperation" in data:
        await bot.send_message(chat_id=chat_id, text=_("Операция отменена", chat_id=chat_id))
        try:
            users[chat_id]["mode_send_to_admins"] = False
            admins[chat_id]['mode_edit_about'] = False
        except KeyError:
            pass

    elif data in currencies and data != "Default":
        currencies.__delitem__(data)
        await bot.send_message(chat_id=chat_id,text=f"Валюта {data} удалена")

    elif "Active" in data:
        currency = data.split()[1]
        current_state = int(currencies[currency]['Active'])
        current_state ^= 1
        currencies[currency]['Active'] = current_state
        await bot.send_message(chat_id=chat_id,text=f"Состояние валюты {currency} переключено")

    elif "Balance" in data:
        currency = data.split()[1]
        await query.message.edit_text(text=await getBalanceInfo(chat_id, currency))
        inline_markup = []
        for currency in list(currencies.keys())[1:]:
            if currencies[currency]['Active'] == 1:
                inline_markup.append(InlineKeyboardButton(text=currency, callback_data=f"Balance {currency}"))
        if not inline_markup:
            inline_markup.append(InlineKeyboardButton(text=_("Нет валют", chat_id), callback_data='None'))
        inline_markup = InlineKeyboardMarkup(inline_keyboard=[inline_markup])
        try:
            await query.message.edit_reply_markup(reply_markup=inline_markup)
        except:
            pass

    # Button "Payed"
    elif "Payed" in data:
        currency = data.split()[1]
        user_chatid = int(data.split()[2])
        sum_payed = data.split()[3]
        if pay_requests[user_chatid] == 0:
            users[user_chatid]['Payed'] += float(sum_payed) / currencies[currency]['Referrals']
            await bot.send_message(chat_id=user_chatid,text=f"{_('Вам выплачено', user_chatid)} "
                                                              f"{sum_payed} {currency}")
            pay_requests[user_chatid] = username
        else:
            await query.answer(text=f"Выплата уже была произведена админом {pay_requests[user_chatid]}",show_alert=True)

    # Delete from chat's monitoring
    elif "Chat" == data.split()[0]:
        global allowed_chats
        chat = data.split()[1]
        allowed_chats = [x for x in allowed_chats if x != chat]
        await query.answer(text=f"Чат с ID: {chat} удален", show_alert=True)
        markup = await getAllowedChats()
        await query.message.edit_reply_markup(reply_markup=markup)

    # Append chat to monitoring's chats
    elif "ChatAppend" in data:
        admins[chat_id]['mode_append_chat'] = 1
        await bot.send_message(chat_id=chat_id,text="Введите ID чата")

    # Append to admins
    elif "Append Admin" == data:
        await bot.send_message(chat_id=chat_id,text="Введите имя пользователя")
        admins[chat_id]['mode_append'] = True

    # Delete from admin
    elif "Admin" in data:
        deladmin = data.split()[1]
        await deletefromAdmin(chat_id, int(deladmin))

    # Choose currency in balance menu
    elif "ChooseCurrency" in data:
        currency = data.split()[1]
        users[chat_id]['pay_request_mode'] = {'currency': currency}
        balance = await getBalance(chat_id, currency) - \
                  users[chat_id]['Payed'] * currencies[currency]['Referrals']
        if balance <= 0:
            message_text = f"{_('В данный момент у вас недостаточно средств для выплаты в', chat_id)} {currency}"
            users[chat_id]['pay_request_mode'] = 0
        else:
            message_text = f"{_('Ваш доступный баланс в', chat_id)} {currency}: " \
                           f"{floatHumanize(balance)}" \
                           f"\n{_('Введите сумму', chat_id=chat_id)}"
        await bot.send_message(chat_id=chat_id, text=message_text)

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
        await bot.send_message(chat_id=chat_id, text=f"Вы забанили пользователя с Chat ID {user_id}")
        logger.info(f"Админ {chat_id} забанил {user_id}")

    await query.answer()

async def sendtoAdmins(text, parse_mode=None, reply_markup=None):
    """Отправляет всем админам сообщение"""
    try:
        for chat_id in admins:
                await bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup, parse_mode=parse_mode)
    except Exception as e:
        logger.error(e)

def saveParams():
    """Сохраняет настройки (текст приветствия, валюты, бонусы) в файл"""
    logger.info("Save params to file")
    with shelve.open('params.db') as params:
        params['start_message'] = start_message
        params['currencies'] = currencies
        params['allowed_chats'] = allowed_chats
        params['about'] = about
        params['banlist'] = banlist

def loadParams():
    """Загружает настройки из файла"""
    global start_message, currencies, allowed_chats, about, banlist
    logger.info("Loading params from file")
    with shelve.open('params.db') as params:
        try:
            start_message = params['start_message']
            currencies = params['currencies']
            allowed_chats = params['allowed_chats']
            about = params['about']
            banlist = params['banlist']
        except Exception as e:
            logger.error(f"Ошибка при загрузке параметров {e}")


@dp.async_task
async def job_queue():
    await asyncio.sleep(60*30)
    saveToDB()


def saveToDB():
    """Сохраняет или обновляет записи в БД"""
    saveParams()
    logger.info("Save and sync database...")
    con = pymysql.connect('localhost', userdb, passworddb, namedb)
    with con:
        curs = con.cursor()
        for chat_id in users:
            username = users[chat_id]['Username']
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

def loadfromDB():
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
            users[chat_id]['Username'] = row[0]
            users[chat_id]['Messages'] = row[3]
            users[chat_id]['Inviter'] = row[4]
            users[chat_id]['Referrals'] = row[2]
            users[chat_id]['Language'] = row[5]
            users[chat_id]['Payed'] = row[7]
            users[chat_id]['pay_request_mode'] = 0
            if row[6] == 1:
                admins[chat_id] = {'mode_append': False, 'change_welcome': False}


@dp.message_handler(lambda message: ChatType.is_group_or_super_group(message), content_types=ContentTypes.TEXT)
async def messageGroup(message=types.Message):
    """Обработчик текстовых сообщений в чате"""
    if not message:
        return 0
    userid = message.from_user.id
    chatmessage_name = message.chat.username
    if chatmessage_name in allowed_chats:
        try:
            users[userid]['Messages'] += 1
        except KeyError:
            pass

async def getStatusInChats(userid, chats):
    for chat in chats:
        try:
            status = (await bot.get_chat_member(user_id=userid, chat_id=f"@{chat}")).status
        except:
            status = 'Not found'
        finally:
            if status in ['creator', 'administrator', 'member', 'restricted']:
                return True
    return False


@dp.message_handler(lambda message: ChatType.is_private(message), commands='unban')
async def unban(message=types.Message):
    global banlist
    chat_id = message.from_user.id
    if chat_id in admins:
        try:
            banlist = [x for x in banlist if x != int(message.get_args()[0])]
            await bot.send_message(chat_id=chat_id, text="Разбанен")
        except:
            await bot.send_message(chat_id=chat_id, text="Ошибка")


if __name__ == "__main__":
    loadfromDB()

    logger.info("Starting....")

    executor.start_polling(dp)

    atexit.register(saveToDB)