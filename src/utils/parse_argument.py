from typing import Any, Dict

from src.utils.logger_config import logger


def parse_arguments(tokens, arg_definitions: Dict[str, Any]):
    """
    Универсальная функция парсинга аргументов.

    :param tokens: список токенов (слова, которые идут после команды),
                   например ["5", "max_len=10", "prefix=hello"].
    :param arg_definitions: словарь с описанием аргументов:
           {
             "имя_аргумента": (тип, значение_по_умолчанию),
             ...
           }
    :return: словарь вида {"min_len": 5, "max_len": 10, ...} со всеми заполненными значениями
    """

    # 1. Инициализируем результирующий словарь значениями по умолчанию.
    results = {}
    for arg_name, (arg_type, default_value) in arg_definitions.items():
        results[arg_name] = default_value

    # 2. Подготовим список аргументов, которым ещё не назначили значение напрямую.
    #    Это нужно, чтобы можно было "по порядку" заполнять значения, например, просто числами.
    remaining_args = list(arg_definitions.keys())

    # 3. Проходимся по каждому токену.
    i = 0
    while i < len(tokens):
        token = tokens[i]

        # Проверяем форму "ключ=значение"
        if "=" in token:
            key, value = token.split("=", 1)
            key = key.strip()
            value = value.strip()

            # Если такой ключ есть среди наших аргументов
            if key in arg_definitions:
                arg_type = arg_definitions[key][0]
                try:
                    # Преобразуем к нужному типу
                    casted_value = arg_type(value)
                    results[key] = casted_value
                    # Удаляем из remaining_args, если он там есть
                    if key in remaining_args:
                        remaining_args.remove(key)
                except ValueError:
                    logger.warning(
                        f"Не удалось преобразовать аргумент '{key}' к типу {arg_type.__name__}. "
                        f"Используется значение по умолчанию."
                    )
            else:
                logger.warning(f"Неизвестный аргумент: '{key}' пропущен.")
            i += 1
            continue

        # Проверяем, не является ли токен именем аргумента, за которым следует значение
        if token in arg_definitions:
            arg_type = arg_definitions[token][0]
            # Берём следующее слово, если оно есть
            if i + 1 < len(tokens):
                next_token = tokens[i + 1]
                try:
                    casted_value = arg_type(next_token)
                    results[token] = casted_value
                    if token in remaining_args:
                        remaining_args.remove(token)
                    i += 2
                    continue
                except ValueError:
                    logger.warning(
                        f"Не удалось преобразовать '{next_token}' к типу {arg_type.__name__}. "
                        f"Аргумент '{token}' остается со значением по умолчанию."
                    )
                    i += 2
                    continue
            else:
                logger.warning(
                    f"Для аргумента '{token}' не указано значение. "
                    f"Будет использовано значение по умолчанию."
                )
                i += 1
                continue

        # Если это просто число/строка без ключа
        # Попытаемся назначить его первому "свободному" аргументу, если тип совпадает
        assigned = False
        for arg_name in remaining_args:
            arg_type = arg_definitions[arg_name][0]
            try:
                casted_value = arg_type(token)  # Пробуем преобразовать к нужному типу
                results[arg_name] = casted_value
                remaining_args.remove(arg_name)
                assigned = True
                break
            except ValueError:
                # Если не удалось преобразовать — идём дальше
                pass

        if not assigned:
            # Если не привязали ни к одному аргументу, можно обработать как ошибку или просто пропустить
            logger.warning(
                f"Токен '{token}' не удалось привязать ни к одному аргументу, пропускаем."
            )
        i += 1

    return results
