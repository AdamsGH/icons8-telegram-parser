import logging
import shutil
import os
import csv
import requests
import time
from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
from selenium import webdriver
from selenium.webdriver.common.by import By
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Получение токена и списка разрешенных пользователей из переменных окружения
TOKEN = os.getenv('TOKEN')
ALLOWED_USER_IDS = os.getenv('ALLOWED_USER_IDS').split(',')

def start(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    if str(user_id) not in ALLOWED_USER_IDS:
        update.message.reply_text('Вы не авторизованы для выполнения этой команды.')
        return
    update.message.reply_text(f'Привет! Отправь мне URL формата `https://icons8.com/icon/set/nature/dusk` и я скачаю все иконки с этой страницы.', parse_mode='Markdown')
    logger.info(f"User {update.effective_user['username']} started the conversation.")

def handle_url(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    if str(user_id) not in ALLOWED_USER_IDS:
        update.message.reply_text('Вы не авторизованы для выполнения этой команды.')
        return

    def download_file(name, srcset, folder_name):
        img_url = srcset.split(' ')[0]
        response = requests.get(img_url)

        with open(f'{folder_name}/{name}.png', 'wb') as img_file:
            img_file.write(response.content)

    def download_files_from_csv(csv_filename, folder_name):
        os.makedirs(folder_name, exist_ok=True)

        with open(csv_filename, 'r', encoding='utf-8') as file:
            reader = csv.reader(file)
            next(reader)

            with ThreadPoolExecutor(max_workers=10) as executor:
                for row in reader:
                    if len(row) == 3:
                        name, srcset, _ = row
                        executor.submit(download_file, name, srcset, folder_name)

    def process_url(url):
        logger.info(f"User {update.effective_user['username']} requested icons from {url}.")

        try:
            driver = webdriver.Remote(
                command_executor='http://selenium:4444/wd/hub',
                desired_capabilities={'browserName': 'chrome', 'javascriptEnabled': True}
            )

            driver.get(url)

            SCROLL_PAUSE_TIME = 2

            while True:
                icons = driver.find_elements(By.CSS_SELECTOR, 'div.grid-icons__item.app-grid-icon')
                if icons:
                    driver.execute_script("arguments[0].scrollIntoView();", icons[-1])

                time.sleep(SCROLL_PAUSE_TIME)

                new_icons = driver.find_elements(By.CSS_SELECTOR, 'div.grid-icons__item.app-grid-icon')
                if len(new_icons) <= len(icons):
                    break

            icons = driver.find_elements(By.CSS_SELECTOR, 'div.grid-icons__item.app-grid-icon')

            soup = BeautifulSoup(driver.page_source, 'html.parser')

            icons = soup.find_all('div', class_='grid-icons__item app-grid-icon')

            if not icons:
                print("No icons found on the page.")
                exit(1)

            folder_name = url.split('/')[-2]

            with open('icons.csv', 'w', newline='', encoding='utf-8') as file:
                writer = csv.writer(file)
                writer.writerow(['Name', 'Srcset', 'Href'])

                for icon in icons:
                    a_tag = icon.find('a', class_='app-grid-icon__link')
                    img_tag = icon.find('img')
                    name = img_tag.get('alt', '').replace(' icon', '')
                    srcset = img_tag.get('srcset')
                    href = a_tag.get('href')

                    srcset = srcset.replace('size=48', 'size=1024').replace('size=96', 'size=1024')

                    writer.writerow([name, srcset, href])

            download_files_from_csv('icons.csv', 'icons/' + folder_name)
            logger.info(f"Icons from {url} downloaded.")

        except Exception as e:
            logger.error(f"Error while processing {url}: {e}")
        finally:
            driver.quit()
            time.sleep(2)

    urls = update.message.text.split('\n')  # Разделение текста сообщения на список ссылок по новым строкам
    chat_id = update.message.chat_id

    # Создаем папку для хранения всех папок с иконками
    os.makedirs('icons', exist_ok=True)
    message = context.bot.send_message(chat_id=chat_id, text='Скачиваю иконки')
    
    # Запуск обработки URL в нескольких потоках
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(process_url, url) for url in urls]
        
    # Ожидание завершения всех задач на скачивание
    for future in futures:
        future.result()

    # Упаковка папки 'icons' в архив и отправка его
    
    message_id = message.message_id
    context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text='Скачивание завершено. Создаю архив...')
    shutil.make_archive('icons', 'zip', 'icons')
    context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text="Архив создан, отправляю")
    with open('icons.zip', 'rb') as file:
        context.bot.send_document(chat_id=chat_id, document=file)
    logger.info(f"Icons from {urls} downloaded and sent to user {update.effective_user['username']}.")

    # Удаление папки 'icons' и архива после отправки
    shutil.rmtree('icons')
    os.remove('icons.zip')

def error(update: Update, context: CallbackContext):
    logger.warning('Update "%s" caused error "%s"', update, context.error)

def main() -> None:
    updater = Updater(token=TOKEN)
    dispatcher = updater.dispatcher

    # Добавление обработчиков команд и сообщений
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_url))
    dispatcher.add_error_handler(error)

    # Запуск бота
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
