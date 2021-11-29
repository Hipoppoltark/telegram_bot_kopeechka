import logging
import requests
from aiogram import Bot, Dispatcher, executor, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.dispatcher.filters import Text
from aiogram.dispatcher import FSMContext
import asyncio
import os
import re


STANDARD_TOKEN = os.environ.get("STANDARD_TOKEN")
ACCESS_TOKEN = os.environ.get("ACCESS_TOKEN")

# Объект бота
bot = Bot(token=ACCESS_TOKEN)
# Диспетчер для бота
dp = Dispatcher(bot, storage=MemoryStorage())
# Включаем логирование, чтобы не пропустить важные сообщения
logging.basicConfig(level=logging.INFO)


def parse_facebook(text):
    """Парсинг письма с Facebook"""
    result = re.findall(r'>(\d{8})<', text)
    if not result:
        return "Письмо не спарсилось"
    return "".join(result)


def get_reply_keyboard(buttons: list, time=False):
    """Получение объекта клавиатуры с помощью списка с названиями кнопок"""
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=time)
    keyboard.add(*buttons)
    return keyboard


class Form(StatesGroup):
    services = State()
    email = State()
    send_message = State()


async def set_default_commands(dp):
    """Стандартные команды для бота"""
    await dp.bot.set_my_commands([
        types.BotCommand("start", "Услуги"),
        types.BotCommand("cancel", "Отменить")
    ])


@dp.message_handler(commands="start")
async def start_command(message: types.Message):
    """Хэндлер на команду /start"""
    keyboard = get_reply_keyboard(["Получить код с почты kopeechka.store📧"])
    await Form.services.set()
    await message.answer("Выберите услугу", reply_markup=keyboard)


@dp.message_handler(state='*', commands='cancel')
@dp.message_handler(Text(equals='отмена', ignore_case=True), state='*')
async def cancel_handler_state(message: types.Message, state: FSMContext):
    """Добавляем возможность отмены, если пользователь передумал заполнять"""
    current_state = await state.get_state()
    if current_state is None:
        return
    await state.finish()
    await message.reply('Хорошо')


@dp.message_handler(commands='cancel')
@dp.message_handler(Text(equals='отмена', ignore_case=True), state='*')
async def cancel_handler(message: types.Message):
    """Добавляем возможность отмены, если пользователь передумал заполнять"""
    await message.reply('Вы еще не начали работу с ботом. Для старта введите /start')


@dp.message_handler()
async def description_bot(message: types.Message):
    """Описание бота"""
    await message.answer("Это бот для получения писем с Facebook.\n"
                         "Для выбора услуги введите /start\n"
                         "Для отмены получения письма с почты введите /cansel\n")


@dp.message_handler(lambda message: message.text != "Получить код с почты kopeechka.store📧",
                    state=Form.services)
async def check_correctness_name_service(message: types.Message):
    """Обработка неправильно введеной услуги"""
    await message.reply("Введите корректную услугу.")


@dp.message_handler(state=Form.services)
async def process_site(message: types.Message, state: FSMContext):
    """Спрашиваем email у пользователя"""
    async with state.proxy() as data:
        data['site'] = "facebook.com"
        await Form.email.set()
        await message.reply("Введите свой email")


@dp.message_handler(state=Form.email)
async def process_get_email(message: types.Message, state: FSMContext):
    """Сохраняем email"""
    async with state.proxy() as data:
        data['email'] = message.text
        keyboard = get_reply_keyboard(["Код отправлен"])
        await message.answer(f"Сейчас активируем почту...")
        response = requests.get(
            'http://api.kopeechka.store/mailbox-reorder',
            params={'token': STANDARD_TOKEN,
                    'site': data['site'],
                    'email': data['email'],
                    'type': 'json',
                    'api': '2.0'},
        )
        response = response.json()
        if response['status'] == 'OK':
            data['task_id'] = response['id']
            await Form.next()
            await message.answer("Почта активирована.")
            await message.answer(f"На сайте {data['site']} нажмите "
                                 f"получить код по почте, после этого нажмите 'Код отправлен'",
                                 reply_markup=keyboard)
        else:
            await message.answer("API или email или сайт не корректны, поробуйте заново ввести их",
                                 reply_markup=get_reply_keyboard(["Получить код с почты kopeechka.store📧"]))
            await Form.services.set()


async def background_on_action(task_id, message, site) -> None:
    """background task which is created when user asked"""
    keyboard = get_reply_keyboard(["Получить код с почты kopeechka.store📧"])
    await asyncio.sleep(8)
    if site == "facebook.com":
        await asyncio.sleep(6)
    response = requests.get(
        'http://api.kopeechka.store/mailbox-get-message',
        params={'full': '0',
                'id': task_id,
                'token': STANDARD_TOKEN,
                'type': 'json',
                'api': '2.0'},
    )
    response = response.json()
    if response['status'] == "OK":
        if site == "facebook.com":
            message_email = parse_facebook(response['fullmessage'])
        else:
            message_email = response['fullmessage']
        await bot.send_message(message.from_user.id, message_email, reply_markup=keyboard)
        await Form.services.set()
    else:
        await bot.send_message(message.from_user.id,
                               "Вы не отправили письмо или оно еще не пришло."
                               "Отправьте его повторно или нажмите 'Код отправлен'",
                               reply_markup=get_reply_keyboard(["Код отправлен"]))


@dp.message_handler(lambda message: message.text == "Код отправлен",
                    state=Form.send_message)
async def process_get_code(message: types.Message, state: FSMContext):
    """Отправляем запрос на сайт копеечки"""
    await message.answer("Сейчас получим код")
    async with state.proxy() as data:
        task_id = data['task_id']
        asyncio.create_task(background_on_action(task_id, message, data['site']))


if __name__ == "__main__":
    # Запуск бота
    executor.start_polling(dp, skip_updates=True, on_startup=set_default_commands)
