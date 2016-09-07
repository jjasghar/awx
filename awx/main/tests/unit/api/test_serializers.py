# Python
import pytest
import mock
from mock import PropertyMock
import json

# AWX
from awx.api.serializers import (
    JobTemplateSerializer,
    JobSerializer,
    JobOptionsSerializer,
    CustomInventoryScriptSerializer,
)
from awx.api.views import JobTemplateDetail
from awx.main.models import (
    Role,
    Label,
    Job,
    CustomInventoryScript,
    User,
)

#DRF
from rest_framework.request import Request
from rest_framework import serializers
from rest_framework.test import (
    APIRequestFactory,
    force_authenticate,
)


def mock_JT_resource_data():
    return ({}, [])

@pytest.fixture
def job_template(mocker):
    mock_jt = mocker.MagicMock(pk=5)
    mock_jt.resource_validation_data = mock_JT_resource_data
    return mock_jt

@pytest.fixture
def job(mocker, job_template):
    return mocker.MagicMock(pk=5, job_template=job_template)

@pytest.fixture
def labels(mocker):
    return [Label(id=x, name='label-%d' % x) for x in xrange(0, 25)]

@pytest.fixture
def jobs(mocker):
    return [Job(id=x, name='job-%d' % x) for x in xrange(0, 25)]

class GetRelatedMixin:
    def _assert(self, model_obj, related, resource_name, related_resource_name):
        assert related_resource_name in related
        assert related[related_resource_name] == '/api/v1/%s/%d/%s/' % (resource_name, model_obj.pk, related_resource_name)

    def _mock_and_run(self, serializer_class, model_obj):
        serializer = serializer_class()
        related = serializer.get_related(model_obj)
        return related

    def _test_get_related(self, serializer_class, model_obj, resource_name, related_resource_name):
        related = self._mock_and_run(serializer_class, model_obj)
        self._assert(model_obj, related, resource_name, related_resource_name)
        return related

class GetSummaryFieldsMixin:
    def _assert(self, summary, summary_field_name):
        assert summary_field_name in summary

    def _mock_and_run(self, serializer_class, model_obj):
        serializer = serializer_class()
        return serializer.get_summary_fields(model_obj)

    def _test_get_summary_fields(self, serializer_class, model_obj, summary_field_name):
        summary = self._mock_and_run(serializer_class, model_obj)
        self._assert(summary, summary_field_name)
        return summary

@mock.patch('awx.api.serializers.UnifiedJobTemplateSerializer.get_related', lambda x,y: {})
@mock.patch('awx.api.serializers.JobOptionsSerializer.get_related', lambda x,y: {})
class TestJobTemplateSerializerGetRelated(GetRelatedMixin):
    @pytest.mark.parametrize("related_resource_name", [
        'jobs',
        'schedules',
        'activity_stream',
        'launch',
        'notification_templates_any',
        'notification_templates_success',
        'notification_templates_error',
        'survey_spec',
        'labels',
        'callback',
    ])
    def test_get_related(self, job_template, related_resource_name):
        self._test_get_related(JobTemplateSerializer, job_template, 'job_templates', related_resource_name)

    def test_callback_absent(self, job_template):
        job_template.host_config_key = None
        related = self._mock_and_run(JobTemplateSerializer, job_template)
        assert 'callback' not in related

class TestJobTemplateSerializerGetSummaryFields(GetSummaryFieldsMixin):
    def test__recent_jobs(self, mocker, job_template, jobs):

        job_template.jobs.all = mocker.MagicMock(**{'order_by.return_value': jobs})
        job_template.jobs.all.return_value = job_template.jobs.all

        serializer = JobTemplateSerializer()
        recent_jobs = serializer._recent_jobs(job_template)

        job_template.jobs.all.assert_called_once_with()
        job_template.jobs.all.order_by.assert_called_once_with('-created')
        assert len(recent_jobs) == 10
        for x in jobs[:10]:
            assert recent_jobs == [{'id': x.id, 'status': x.status, 'finished': x.finished} for x in jobs[:10]]

    def test_survey_spec_exists(self, mocker, job_template):
        job_template.survey_spec = {'name': 'blah', 'description': 'blah blah'}
        self._test_get_summary_fields(JobTemplateSerializer, job_template, 'survey')

    def test_survey_spec_absent(self, mocker, job_template):
        job_template.survey_spec = None
        summary = self._mock_and_run(JobTemplateSerializer, job_template)
        assert 'survey' not in summary

    def test_copy_edit_standard(self, mocker, job_template_factory):
        """Verify that the exact output of the access.py methods
        are put into the serializer user_capabilities"""

        jt_obj = job_template_factory('testJT', project='proj1', persisted=False).job_template
        jt_obj.id = 5
        jt_obj.admin_role = Role(id=9, role_field='admin_role')
        jt_obj.execute_role = Role(id=8, role_field='execute_role')
        jt_obj.read_role = Role(id=7, role_field='execute_role')
        user = User(username="auser")
        serializer = JobTemplateSerializer(job_template)
        serializer.show_capabilities = ['copy', 'edit']
        serializer._summary_field_labels = lambda self: []
        serializer._recent_jobs = lambda self: []
        request = APIRequestFactory().get('/api/v1/job_templates/42/')
        request.user = user
        view = JobTemplateDetail()
        view.request = request
        serializer.context['view'] = view

        with mocker.patch("awx.main.access.JobTemplateAccess.can_change", return_value='foobar'):
            with mocker.patch("awx.main.access.JobTemplateAccess.can_add", return_value='foo'):
                response = serializer.get_summary_fields(jt_obj)

        assert response['user_capabilities']['copy'] == 'foo'
        assert response['user_capabilities']['edit'] == 'foobar'

@mock.patch('awx.api.serializers.UnifiedJobTemplateSerializer.get_related', lambda x,y: {})
@mock.patch('awx.api.serializers.JobOptionsSerializer.get_related', lambda x,y: {})
class TestJobSerializerGetRelated(GetRelatedMixin):
    @pytest.mark.parametrize("related_resource_name", [
        'job_events',
        'job_plays',
        'job_tasks',
        'relaunch',
        'labels',
    ])
    def test_get_related(self, mocker, job, related_resource_name):
        self._test_get_related(JobSerializer, job, 'jobs', related_resource_name)

    def test_job_template_absent(self, mocker, job):
        job.job_template = None
        serializer = JobSerializer()
        related = serializer.get_related(job)
        assert 'job_template' not in related

    def test_job_template_present(self, job):
        related = self._mock_and_run(JobSerializer, job)
        assert 'job_template' in related
        assert related['job_template'] == '/api/v1/%s/%d/' % ('job_templates', job.job_template.pk)

@mock.patch('awx.api.serializers.BaseSerializer.to_representation', lambda self,obj: {
    'extra_vars': obj.extra_vars})
class TestJobSerializerSubstitution():

    def test_survey_password_hide(self, mocker):
        job = mocker.MagicMock(**{
            'display_extra_vars.return_value': '{\"secret_key\": \"$encrypted$\"}',
            'extra_vars.return_value': '{\"secret_key\": \"my_password\"}'})
        serializer = JobSerializer(job)
        rep = serializer.to_representation(job)
        extra_vars = json.loads(rep['extra_vars'])
        assert extra_vars['secret_key'] == '$encrypted$'
        job.display_extra_vars.assert_called_once_with()
        assert 'my_password' not in extra_vars

@mock.patch('awx.api.serializers.BaseSerializer.get_summary_fields', lambda x,y: {})
class TestJobOptionsSerializerGetSummaryFields(GetSummaryFieldsMixin):
    def test__summary_field_labels_10_max(self, mocker, job_template, labels):
        job_template.labels.all = mocker.MagicMock(**{'order_by.return_value': labels})
        job_template.labels.all.return_value = job_template.labels.all

        serializer = JobOptionsSerializer()
        summary_labels = serializer._summary_field_labels(job_template)

        job_template.labels.all.order_by.assert_called_with('name')
        assert len(summary_labels['results']) == 10
        assert summary_labels['results'] == [{'id': x.id, 'name': x.name} for x in labels[:10]]

    def test_labels_exists(self, mocker, job_template):
        self._test_get_summary_fields(JobOptionsSerializer, job_template, 'labels')

class TestJobTemplateSerializerValidation(object):

    good_extra_vars = ["{\"test\": \"keys\"}", "---\ntest: key"]
    bad_extra_vars = ["{\"test\": \"keys\"", "---\ntest: [2"]

    def test_validate_extra_vars(self):
        serializer = JobTemplateSerializer()
        for ev in self.good_extra_vars:
            serializer.validate_extra_vars(ev)
        for ev in self.bad_extra_vars:
            with pytest.raises(serializers.ValidationError):
                serializer.validate_extra_vars(ev)

class TestCustomInventoryScriptSerializer(object):

    @pytest.mark.parametrize("superuser,sysaudit,admin_role,value",
                             ((True, False, False, '#!/python'),
                              (False, True, False, '#!/python'),
                              (False, False, True, '#!/python'),
                              (False, False, False, None)))
    def test_to_representation_orphan(self, superuser, sysaudit, admin_role, value):
        with mock.patch.object(CustomInventoryScriptSerializer, 'get_summary_fields', return_value={}):
                User.add_to_class('is_system_auditor', sysaudit)
                user = User(username="root", is_superuser=superuser)
                roles = [user] if admin_role else []

                with mock.patch('awx.main.models.CustomInventoryScript.admin_role', new_callable=PropertyMock, return_value=roles):
                    cis = CustomInventoryScript(pk=1, script='#!/python')
                    serializer = CustomInventoryScriptSerializer()

                    factory = APIRequestFactory()
                    wsgi_request = factory.post("/inventory_script/1", {'id':1}, format="json")
                    force_authenticate(wsgi_request, user)

                    request = Request(wsgi_request)
                    serializer.context['request'] = request

                    representation = serializer.to_representation(cis)
                    assert representation['script'] == value
