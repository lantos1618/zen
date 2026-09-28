"""Protect review provenance and keep malformed model output out of rankings."""
import copy
import unittest

import jev_test_review as review


class ReviewContracts(unittest.TestCase):
    def response(self):
        answers = {}
        for name, question in review.QUESTIONS.items():
            answer = dict(type=question['type'], confidence=.8)
            if question['type'] == 'score':
                answer['score'] = 3
            else:
                answer['choice'] = next(iter(question['criteria']))
            answers[name] = answer
        return dict(model=review.MODEL, answers=answers)

    def test_missing_answer_is_not_a_completed_review(self):
        response = self.response()
        del response['answers']['oracle_strength']
        with self.assertRaises(ValueError):
            review.validate(response)

    def test_nonfinite_or_out_of_range_scores_are_refused(self):
        for value in (float('nan'), float('inf'), -1, 5, '3'):
            response = self.response()
            response['answers']['oracle_strength']['score'] = value
            with self.assertRaises(ValueError):
                review.validate(response)

    def test_unrecognized_action_cannot_enter_ranking(self):
        response = self.response()
        response['answers']['recommendation']['choice'] = 'delete_everything'
        with self.assertRaises(ValueError):
            review.validate(response)

    def test_request_identity_changes_with_source_or_oracle(self):
        row = dict(files=[dict(path='sample.zen', text='main = () {}')], expected_exit=0)
        first = review.digest(review.packet(row))
        changed = copy.deepcopy(row)
        changed['expected_exit'] = 1
        self.assertNotEqual(first, review.digest(review.packet(changed)))
        changed = copy.deepcopy(row)
        changed['files'][0]['text'] += '\n// another contract'
        self.assertNotEqual(first, review.digest(review.packet(changed)))

    def test_large_context_is_marked_and_local_source_preserved(self):
        row = dict(files=[dict(path='big.zen', text='x' * 90000)])
        payload = review.packet(row)
        state = payload['state']['test']
        self.assertEqual(state['context_truncated_files'], ['big.zen'])
        self.assertEqual(state['files'][0]['omitted_characters'], 42000)
        self.assertEqual(len(row['files'][0]['text']), 90000)

    def test_cross_origin_redirect_never_forwards_credential(self):
        self.assertIsNone(review.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://other.invalid'))


if __name__ == '__main__':
    unittest.main()
