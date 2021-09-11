import logging
import requests
from aiogram import Bot, Dispatcher, executor, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.dispatcher.filters import Text
from aiogram.dispatcher import FSMContext
import os


STANDARD_TOKEN = os.environ.get("STANDARD_TOKEN")


# Объект бота
bot = Bot(token="1913319721:AAFPa-vvm1RMBBcg3Ya5jpsrFNUb0m5N8nA")
# Диспетчер для бота
dp = Dispatcher(bot, storage=MemoryStorage())
# Включаем логирование, чтобы не пропустить важные сообщения
logging.basicConfig(level=logging.INFO)


def get_reply_keyboard(buttons: list):
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(*buttons)
    return keyboard


class Form(StatesGroup):
    services = State()
    site = State()
    email = State()
    send_message = State()


async def set_default_commands(dp):
    await dp.bot.set_my_commands([
        types.BotCommand("start", "Услуги"),
        types.BotCommand("cancel", "Отменить")
    ])


# Хэндлер на команду /start
@dp.message_handler(commands="start")
async def cmd_test1(message: types.Message):
    keyboard = get_reply_keyboard(["Получить код с почты kopeechka.store📧"])
    await Form.services.set()
    await message.answer("Выберите услугу", reply_markup=keyboard)


# Добавляем возможность отмены, если пользователь передумал заполнять
@dp.message_handler(state='*', commands='cancel')
@dp.message_handler(Text(equals='отмена', ignore_case=True), state='*')
async def cancel_handler_state(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None:
        return

    await state.finish()
    await message.reply('Хорошо')


# Добавляем возможность отмены, если пользователь передумал заполнять
@dp.message_handler(commands='cancel')
@dp.message_handler(Text(equals='отмена', ignore_case=True), state='*')
async def cancel_handler(message: types.Message):
    await message.reply('Вы еще не начали работу с ботом. Для старта введите /start')


"""# Обработка кнопки 'назад'
@dp.message_handler(lambda message: message.text == "назад", state='*')
async def get_previous_state(message: types.Message):
    await Form.previous()"""


# Обработка неправильно введеной услуги
@dp.message_handler(lambda message: message.text != "Получить код с почты kopeechka.store📧",
                    state=Form.services)
async def which_api_key_use_invalid(message: types.Message):
    await message.reply("Введите корректную услугу.")


# Принимаем услугу
# Сюда приходит ответ с типом API KEY
@dp.message_handler(state=Form.services)
async def process_name(message: types.Message, state: FSMContext):
    keyboard = get_reply_keyboard(["facebook.com", "vk.com"])
    await Form.site.set()
    await message.reply("Введите свой сайт или выбиртие из предложенных.", reply_markup=keyboard)


@dp.message_handler(state=Form.site)
async def process_site(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data['site'] = message.text
        await Form.email.set()
        await message.reply("Введите свой email")


# Сохраняем email
@dp.message_handler(state=Form.email)
async def process_get_email(message: types.Message, state: FSMContext):
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


# Отправляем запрос на сайт копеечки
@dp.message_handler(lambda message: message.text == "Код отправлен",
                    state=Form.send_message)
async def process_get_code(message: types.Message, state: FSMContext):
    keyboard = get_reply_keyboard(["Получить код с почты kopeechka.store📧"])
    await message.answer("Сейчас получим код")
    async with state.proxy() as data:
        task_id = data['task_id']
        response = {"value": "WAIT_LINK"}
        i = 0
        while response['value'] == "WAIT_LINK":
            if i == 5:
                await message.answer("Мы не нашли письма, попробуйте все занвово.",
                                     reply_markup=get_reply_keyboard(["Получить код с почты kopeechka.store📧"]))
                await Form.services.set()
                break
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
                await message.answer(response['fullmessage'], reply_markup=keyboard)
                await Form.services.set()
            elif response['status'] == "ERROR" and response['value'] != "WAIT_LINK":
                await message.answer(f"Вы не отправили письмо. Отправьте его повторно или введите /cancel",
                                     reply_markup=get_reply_keyboard(["Код отправлен"]))
                break
            i += 1


if __name__ == "__main__":
    # Запуск бота
    executor.start_polling(dp, skip_updates=True, on_startup=set_default_commands)
