from dateutil import parser
import json
from pathlib import Path

import pytest

from mesosim.warning import process_warning_text

@pytest.fixture(scope='session')
def warning_text(request):
    with open(Path(__file__).parent / "testfiles/svroax_202107100300Z.json", "r") as f:
        data = json.load(f)
    for result in data['results']:
        if result['utcvalid'] == request.param:
            return request.param, result['data']

@pytest.mark.parametrize('warning_text', ['2021-07-10T03:12Z'], indirect=True)
@pytest.mark.parametrize('new_time', ['2022-03-30T17:00Z'])
def test_warning_parsing_basic(warning_text, new_time):
    timings = {
        'arc_start_time': warning_text[0],
        'cur_start_time': new_time,
        'speed_factor': 4
    }

    new_text, new_valid = process_warning_text(warning_text[1], timings)
    new_text_lines = new_text.split("\r\r\n")

    # Check the control header
    assert (
        new_text_lines[5].split(".")[-1][0:12]
        == new_time.replace("-", "").replace(":", "")[2:]
    )
    assert (
        new_text_lines[5].split(".")[-1][13:17]
        == new_time.replace("-", "").replace(":", "")[2:6]
    )

    # Check the other lines
    if new_time == '2022-03-30T17:00Z':
        assert new_text_lines[10] == '1200 PM CDT WED MAR 30 2022'
        assert new_text_lines[23] == '* Until 1212 PM CDT.'
        assert new_text_lines[25][2:16] == 'At 1159 AM CDT'
        assert new_text_lines[37][-12:-1] == '1200 PM CDT'
        assert new_text_lines[38][-12:-1] == '1203 PM CDT'
        assert new_text_lines[39][-12:-1] == '1204 PM CDT'
