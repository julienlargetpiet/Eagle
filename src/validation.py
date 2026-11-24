"""Validate the shape of generated documents (not factual accuracy)."""

def check_control_characters(value):
    if isinstance(value, str):
        if any(ord(char) < 32 and char not in '\n\t' for char in value):
            raise ValueError('Model output contains invalid control characters')

    elif isinstance(value, dict):
        for item in value.values():
            check_control_characters(item)

    elif isinstance(value, list):
        for item in value:
            check_control_characters(item)

def validate_application(result: dict) -> None:
    if not isinstance(result, dict):
        raise ValueError('Model output must be an object')

    check_control_characters(result)

    for field in ('subject', 'body'):
        if not isinstance(result.get(field), str) or not result[field].strip():
            raise ValueError(f'Invalid model output: {field}')

    letter = result.get('letter')
    if not isinstance(letter, dict):
        raise ValueError('Invalid model output: letter')

    for field in (
        'name', 'email', 'phone', 'city',
        'company', 'company_city', 'date',
        'subject', 'salutation', 'closing'
    ):
        if not isinstance(letter.get(field), str):
            raise ValueError(f'Invalid letter field: {field}')

    paragraphs = letter.get('body')
    if not isinstance(paragraphs, list) or not paragraphs or any(
        not isinstance(paragraph, str) or not paragraph.strip()
        for paragraph in paragraphs
    ):
        raise ValueError('Invalid letter body')

    cv = result.get('cv')
    if not isinstance(cv, dict):
        raise ValueError('Invalid model output: cv')

    for field in ('name', 'headline', 'summary', 'skills'):
        if not isinstance(cv.get(field), str):
            raise ValueError(f'Invalid CV field: {field}')

    for field in ('education', 'experience'):
        if not isinstance(cv.get(field), list):
            raise ValueError(f'Invalid CV field: {field}')

    for item in cv['education']:
        if not isinstance(item, dict) or any(
            not isinstance(item.get(key), str)
            for key in ('degree', 'institution', 'period')
        ):
            raise ValueError('Invalid education entry')

    for item in cv['experience']:
        if not isinstance(item, dict) or any(
            not isinstance(item.get(key), str)
            for key in ('position', 'company', 'period')
        ):
            raise ValueError('Invalid experience entry')

        achievements = item.get('achievements')
        if not isinstance(achievements, list) or any(
            not isinstance(achievement, str)
            for achievement in achievements
        ):
            raise ValueError('Invalid achievements')


