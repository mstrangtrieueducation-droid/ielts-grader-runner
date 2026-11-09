"""Compute the teacher's underlength adjustment from original integer bands only."""
import argparse
import json
from fractions import Fraction


def calculate(task, words, bands):
    if task not in (1, 2) or isinstance(task, bool):
        raise ValueError('task must be 1 or 2')
    if type(words) is not int or words < 0:
        raise ValueError('words must be a non-negative integer')
    if len(bands) != 4 or any(type(b) is not int or not 0 <= b <= 9 for b in bands):
        raise ValueError('Supply four ORIGINAL descriptor integer bands, in TA/TR, CC, LR, GRA order')
    minimum = 150 if task == 1 else 250
    shortfall = max(0, minimum - words)
    deduction = Fraction(0) if not shortfall else Fraction(1, 2) if shortfall * 10 < minimum else Fraction(1)
    labels = ['TA' if task == 1 else 'TR', 'CC', 'LR', 'GRA']
    adjusted = [Fraction(bands[0])] + [max(Fraction(0), Fraction(b) - deduction) for b in bands[1:]]

    def assessment(values):
        mean = sum(values, Fraction(0)) / 4
        return {'criteria': dict(zip(labels, map(float, values))), 'mean': float(mean),
                'overallBand': float((mean * 2 + Fraction(1, 2)) // 1 / 2)}

    return {'task': task, 'wordCount': words, 'minimum': minimum, 'shortfall': shortfall,
            'shortfallPercent': float(Fraction(shortfall * 100, minimum)),
            'deductionPerLanguageCriterion': float(deduction), 'officialIeltsPenalty': False,
            'descriptorAssessment': assessment(bands), 'classAssessment': assessment(adjusted),
            'displayAssessment': 'classAssessment'}


def self_test():
    for task, words, expected in [(1,150,0),(1,149,.5),(1,136,.5),(1,135,1),
                                  (2,250,0),(2,249,.5),(2,226,.5),(2,225,1),(2,186,1)]:
        result = calculate(task, words, [5,6,6,6])
        assert result['deductionPerLanguageCriterion'] == expected
        assert result['classAssessment']['criteria']['TA' if task == 1 else 'TR'] == 5
    assert calculate(2,186,[5,6,6,6])['classAssessment']['overallBand'] == 5
    assert calculate(2,250,[5,5,5,6])['classAssessment']['overallBand'] == 5.5
    assert calculate(2,249,[5,5,5,5])['classAssessment']['overallBand'] == 4.5
    assert calculate(2,0,[0,0,0,0])['classAssessment']['mean'] == 0
    try:
        calculate(2,240,[5,5.5,6,6])
    except ValueError:
        pass
    else:
        raise AssertionError('Fractional/adjusted inputs must be rejected')
    print('PASS: thresholds, TA/TR preservation, half-up rounding, floor and input checks')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--task', type=int, choices=[1,2])
    parser.add_argument('--words', type=int)
    parser.add_argument('--bands', type=int, nargs=4, metavar=('TA_TR','CC','LR','GRA'))
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    if args.self_test:
        self_test()
    else:
        if args.task is None or args.words is None or args.bands is None:
            parser.error('--task, --words and --bands are required')
        print(json.dumps(calculate(args.task, args.words, args.bands), ensure_ascii=False, indent=2))
