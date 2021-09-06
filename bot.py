import logging
import requests
from aiogram import Bot, Dispatcher, executor, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.dispatcher.filters import Text
from aiogram.dispatcher import FSMContext


STANDART_TOKEN = "308a347c3b38e85bfbc5ae53f6758ade"


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
    type_key = State()
    api_key = State()
    site = State()
    email = State()
    send_message = State()


async def set_default_commands(dp):
    await dp.bot.set_my_commands([
        types.BotCommand("start", "Услуги")
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
async def cancel_handler(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None:
        return

    await state.finish()
    await message.reply('Хорошо')


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
@dp.message_handler(state=Form.services)
async def which_api_key_use(message: types.Message):
    keyboard = get_reply_keyboard(["Стандартный API KEY", "Ввести свой API KEY"])
    await Form.type_key.set()
    await message.reply("Какой API ключ использовать?", reply_markup=keyboard)


# Проверяем тип API KEY
@dp.message_handler(lambda message: message.text not in ["Стандартный API KEY", "Ввести свой API KEY"],
                    state=Form.type_key)
async def process_type_key_invalid(message: types.Message):
    return await message.reply("Введите корректный тип API KEY или напиши /cancel")


# Сюда приходит ответ с типом API KEY
@dp.message_handler(state=Form.type_key)
async def process_name(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data['type_api'] = message.text

        if message.text == "Ввести свой API KEY":
            await Form.api_key.set()
            await message.reply("Введите свой API.")
        else:
            data['api_key'] = STANDART_TOKEN
            keyboard = get_reply_keyboard(["facebook.com", "vk.com"])
            await Form.site.set()
            await message.reply("Введите свой сайт или выбиртие из предложенных.", reply_markup=keyboard)


@dp.message_handler(state=Form.site)
async def process_site(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data['site'] = message.text
        await Form.email.set()
        await message.reply("Введите свой email")


# Принимаем API KEY пользователя
@dp.message_handler(state=Form.api_key)
async def get_user_api_key(message: types.Message, state: FSMContext):
    await Form.next()
    await state.update_data(api_key=message.text)
    keyboard = get_reply_keyboard(["facebook.com", "vk.com"])
    await message.reply("Введите свой сайт или выбиртие из предложенных.", reply_markup=keyboard)


# Сохраняем email
@dp.message_handler(state=Form.email)
async def process_get_email(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data['email'] = message.text
        keyboard = get_reply_keyboard(["Код отправлен"])
        await Form.next()
        await message.answer(f"На сайте {data['site']} нажмите "
                             f"получить код по почте, после этого нажмите 'Код отправлен'",
                             reply_markup=keyboard)


# Отправляем запрос на сайт копеечки
@dp.message_handler(lambda message: message.text == "Код отправлен",
                    state=Form.send_message)
async def process_get_code(message: types.Message, state: FSMContext):
    keyboard = get_reply_keyboard(["Получить код с почты kopeechka.store📧"])
    await message.answer("Сейчас получим код")
    async with state.proxy() as data:
        response = requests.get(
            'http://api.kopeechka.store/mailbox-get-fresh-id',
            params={'token': data['api_key'],
                    'site': data['site'],
                    'email': data['email'],
                    'type': 'json',
                    'api': '2.0'},
        )
        response = response.json()
        print(response)
        if response['status'] == 'OK':
            task_id = response['id']
            response = requests.get(
                'http://api.kopeechka.store/mailbox-get-message',
                params={'full': '0',
                        'id': task_id,
                        'token': data['api_key'],
                        'type': 'json',
                        'api': '2.0'},
            )
            response = response.json()
            print(response)
            if response['status'] == "OK":
                await message.answer(response['fullmessage'], reply_markup=keyboard)
                await state.finish()
            elif response['status'] == "ERROR":
                await message.answer("Вы не отправили письмо.",
                                     reply_markup=get_reply_keyboard(["Код отправлен"]))
        else:
            await message.answer("API или email или сайт не корректны, поробуйте заново ввести их",
                                 reply_markup=get_reply_keyboard(["Получить код с почты kopeechka.store📧"]))
            await Form.services.set()


if __name__ == "__main__":
    # Запуск бота
    executor.start_polling(dp, skip_updates=True, on_startup=set_default_commands)
