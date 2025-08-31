ТНС – социальные медиа

### Установка

1. Клонируйте репозиторий на ваш компьютер:

    ```
    git clone git@github.com:MomaPu/THCnews.git
    ```

2. Создайте файл `.env` и заполните его своими параметрами. 
### Сборка Docker-образов

3. Cоздать и активировать виртуальное окружение:

### Для Windows

```
python -m venv venv
```

```
venv/Scripts/activate
```


### Для macOS
```
python3 -m venv env
```

```
source venv/bin/activate
```


Установить зависимости из файла requirements.txt:

```
python -m pip install --upgrade pip
```

```
pip install -r requirements.txt
```


Запустить проект scriptocr.py
```
python main.py
```

### Используемые технологии
- Python 3.11.1  
- Flask 3.1.1
- PostgreSQL 13.10  

### Автор
Семячкин Матвей Витальевич
E-mail: matvey.seymachin@mail.ru
