import json
import contextlib
import io
import pathlib
import tempfile
import unittest
from unittest import mock

import generator_deploy as deploy


class CopyContextTests(unittest.TestCase):
    def test_runner_refuses_production_before_any_work(self):
        for flags in ([],['--i-approve','--containerfile','Containerfile.3d']):
            with self.subTest(flags=flags), contextlib.redirect_stdout(io.StringIO()) as output:
                with mock.patch('sys.argv',['generator_deploy.py','runner',*flags]), mock.patch.object(deploy,'Run') as report, mock.patch.object(deploy,'audit') as audit, mock.patch.object(deploy,'build') as build, mock.patch.object(deploy,'deploy') as promote:
                    self.assertEqual(deploy.main(),2)
                    report.assert_not_called();audit.assert_not_called();build.assert_not_called();promote.assert_not_called()
                self.assertIn('BLOCKED',output.getvalue())
                self.assertIn('tools/watoom-code/deploy-platform.py --blender-toolkit-only',output.getvalue())

    def test_both_maintained_containerfiles_match_deploy_context(self):
        tools=pathlib.Path(__file__).resolve().parent
        for name in ('Containerfile.local-only','Containerfile.3d'):
            with self.subTest(containerfile=name), tempfile.TemporaryDirectory() as tmp:
                recipe=tools/name
                # Independent expectation from the maintained, explicit COPY line.
                lines=[line for line in recipe.read_text().splitlines() if line.startswith('COPY ')]
                self.assertEqual(len(lines),1)
                expected=lines[0].split()[1:-1]
                context=pathlib.Path(tmp)/'context'
                hashes=deploy.copy_context(tools,recipe,context)
                actual={str(p.relative_to(context)) for p in context.rglob('*') if p.is_file()}
                self.assertEqual(actual,set(expected))
                self.assertEqual(set(hashes),set(expected))
                self.assertIn('catalog.json',hashes)
                self.assertIn('creative_verify.gd',hashes)
                for source in expected:
                    self.assertEqual((context/source).read_bytes(),(tools/source).read_bytes())
                    self.assertEqual(hashes[source],deploy.digest(context/source))

    def test_missing_copy_file_fails_before_context_or_builder(self):
        with tempfile.TemporaryDirectory() as tmp:
            tools=pathlib.Path(tmp)
            recipe=tools/'Containerfile.local-only'
            recipe.write_text('FROM fixture\nCOPY present.py missing.gd /opt/watoom/\n')
            (tools/'present.py').write_text('pass\n')
            context=tools/'context'
            with self.assertRaisesRegex(ValueError,'Missing COPY source files: missing.gd'):
                deploy.copy_context(tools,recipe,context)
            self.assertFalse(context.exists())
            report=mock.Mock(out=tools)
            with mock.patch.object(deploy,'TOOLS',tools), mock.patch.object(deploy,'invoke') as invoke:
                self.assertIsNone(deploy.build(report,tools))
                invoke.assert_not_called()
            report.note.assert_called_once_with('COPY_SOURCES','BLOCKED','Missing COPY source files: missing.gd')

    def test_non_python_copy_inputs_are_hashed(self):
        with tempfile.TemporaryDirectory() as tmp:
            tools=pathlib.Path(tmp);recipe=tools/'Containerfile'
            recipe.write_text('FROM fixture\nCOPY catalog.json verify.gd /opt/watoom/\n')
            for name in ('catalog.json','verify.gd'):(tools/name).write_text('original')
            before=deploy.source_hashes(tools,recipe)
            for name in before:
                with self.subTest(source=name):
                    (tools/name).write_text('changed')
                    self.assertNotEqual(before[name],deploy.source_hashes(tools,recipe)[name])
                    (tools/name).write_text('original')

    def test_multiple_json_and_continued_copy_instructions(self):
        with tempfile.TemporaryDirectory() as tmp:
            recipe=pathlib.Path(tmp)/'Containerfile'
            recipe.write_text('FROM fixture\nCOPY one.py '+chr(92)+'\n  two.gd /opt/watoom/\nCOPY ["catalog.json", "one.py", "/opt/watoom/"]\n')
            self.assertEqual(deploy.copy_sources(recipe),['one.py','two.gd','catalog.json'])

    def test_unsupported_or_unsafe_sources_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            recipe=pathlib.Path(tmp)/'Containerfile'
            for source in ('../secret','/secret','*.py','$INPUT','--from=other x.py'):
                with self.subTest(source=source):
                    recipe.write_text('COPY '+source+' /opt/watoom/\n')
                    with self.assertRaises(ValueError):deploy.copy_sources(recipe)


if __name__=='__main__':unittest.main()
