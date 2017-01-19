# -*- coding: utf-8 -*-

import mock # noqa
import pytest

from django.core.urlresolvers import reverse
from awx.main.models import Project


#
# Project listing and visibility tests
#
@pytest.fixture
def team_project_list(organization_factory):
    objects = organization_factory('org-test',
                                   superusers=['admin'],
                                   users=['team1:alice', 'team2:bob'],
                                   teams=['team1', 'team2'],
                                   projects=['pteam1', 'pteam2', 'pshared'],
                                   roles=['team1.member_role:pteam1.admin_role',
                                          'team2.member_role:pteam2.admin_role',
                                          'team1.member_role:pshared.admin_role',
                                          'team2.member_role:pshared.admin_role'])
    return objects


@pytest.mark.django_db
def test_user_project_paged_list(get, organization_factory):
    'Test project listing that spans multiple pages'

    # 3 total projects, 1 per page, 3 pages
    objects = organization_factory(
        'org1',
        projects=['project-%s' % i for i in range(3)],
        users=['alice'],
        roles=['project-%s.admin_role:alice' % i for i in range(3)],
    )

    # first page has first project and no previous page
    pk = objects.users.alice.pk
    url = reverse('api:user_projects_list', args=(pk,))
    results = get(url, objects.users.alice, QUERY_STRING='page_size=1').data
    assert results['count'] == 3
    assert len(results['results']) == 1
    assert results['previous'] is None
    assert results['next'] == (
        '/api/v1/users/%s/projects/?page=2&page_size=1' % pk
    )

    # second page has one more, a previous and next page
    results = get(url, objects.users.alice,
                  QUERY_STRING='page=2&page_size=1').data
    assert len(results['results']) == 1
    assert results['previous'] == (
        '/api/v1/users/%s/projects/?page=1&page_size=1' % pk
    )
    assert results['next'] == (
        '/api/v1/users/%s/projects/?page=3&page_size=1' % pk
    )

    # third page has last project and a previous page
    results = get(url, objects.users.alice,
                  QUERY_STRING='page=3&page_size=1').data
    assert len(results['results']) == 1
    assert results['previous'] == (
        '/api/v1/users/%s/projects/?page=2&page_size=1' % pk
    )
    assert results['next'] is None


@pytest.mark.django_db
def test_user_project_paged_list_with_unicode(get, organization_factory):
    'Test project listing that contains unicode chars in the next/prev links'

    # Create 2 projects that contain a "cloud" unicode character, make sure we
    # can search it and properly generate next/previous page links
    objects = organization_factory(
        'org1',
        projects=['project-☁-1','project-☁-2'],
        users=['alice'],
        roles=['project-☁-1.admin_role:alice','project-☁-2.admin_role:alice'],
    )
    pk = objects.users.alice.pk
    url = reverse('api:user_projects_list', args=(pk,))

    # first on first page, next page link contains unicode char
    results = get(url, objects.users.alice,
                  QUERY_STRING='page_size=1&search=%E2%98%81').data
    assert results['count'] == 2
    assert len(results['results']) == 1
    assert results['next'] == (
        '/api/v1/users/%s/projects/?page=2&page_size=1&search=%%E2%%98%%81' % pk  # noqa
    )

    # second project on second page, previous page link contains unicode char
    results = get(url, objects.users.alice,
                  QUERY_STRING='page=2&page_size=1&search=%E2%98%81').data
    assert results['count'] == 2
    assert len(results['results']) == 1
    assert results['previous'] == (
        '/api/v1/users/%s/projects/?page=1&page_size=1&search=%%E2%%98%%81' % pk  # noqa
    )


@pytest.mark.django_db
def test_user_project_list(get, organization_factory):
    'List of projects a user has access to, filtered by projects you can also see'

    objects = organization_factory('org1',
                                   projects=['alice project', 'bob project', 'shared project'],
                                   superusers=['admin'],
                                   users=['alice', 'bob'],
                                   roles=['alice project.admin_role:alice',
                                          'bob project.admin_role:bob',
                                          'shared project.admin_role:bob',
                                          'shared project.admin_role:alice'])

    assert get(reverse('api:user_projects_list', args=(objects.superusers.admin.pk,)), objects.superusers.admin).data['count'] == 3

    # admins can see everyones projects
    assert get(reverse('api:user_projects_list', args=(objects.users.alice.pk,)), objects.superusers.admin).data['count'] == 2
    assert get(reverse('api:user_projects_list', args=(objects.users.bob.pk,)), objects.superusers.admin).data['count'] == 2

    # users can see their own projects
    assert get(reverse('api:user_projects_list', args=(objects.users.alice.pk,)), objects.users.alice).data['count'] == 2

    # alice should only be able to see the shared project when looking at bobs projects
    assert get(reverse('api:user_projects_list', args=(objects.users.bob.pk,)), objects.users.alice).data['count'] == 1

    # alice should see all projects they can see when viewing an admin
    assert get(reverse('api:user_projects_list', args=(objects.superusers.admin.pk,)), objects.users.alice).data['count'] == 2


@pytest.mark.django_db
def test_team_project_list(get, team_project_list):
    objects = team_project_list

    team1, team2 = objects.teams.team1, objects.teams.team2
    alice, bob, admin = objects.users.alice, objects.users.bob, objects.superusers.admin

    # admins can see all projects on a team
    assert get(reverse('api:team_projects_list', args=(team1.pk,)), admin).data['count'] == 2
    assert get(reverse('api:team_projects_list', args=(team2.pk,)), admin).data['count'] == 2

    # users can see all projects on teams they are a member of
    assert get(reverse('api:team_projects_list', args=(team1.pk,)), alice).data['count'] == 2

    # but if she does, then she should only see the shared project
    team2.read_role.members.add(alice)
    assert get(reverse('api:team_projects_list', args=(team2.pk,)), alice).data['count'] == 1
    team2.read_role.members.remove(alice)

    # admins can see all projects
    assert get(reverse('api:user_projects_list', args=(admin.pk,)), admin).data['count'] == 3

    # admins can see everyones projects
    assert get(reverse('api:user_projects_list', args=(alice.pk,)), admin).data['count'] == 2
    assert get(reverse('api:user_projects_list', args=(bob.pk,)), admin).data['count'] == 2

    # users can see their own projects
    assert get(reverse('api:user_projects_list', args=(alice.pk,)), alice).data['count'] == 2

    # alice should see all projects they can see when viewing an admin
    assert get(reverse('api:user_projects_list', args=(admin.pk,)), alice).data['count'] == 2


@pytest.mark.django_db
def test_team_project_list_fail1(get, team_project_list):
    objects = team_project_list
    res = get(reverse('api:team_projects_list', args=(objects.teams.team2.pk,)), objects.users.alice)
    assert res.status_code == 403


@pytest.mark.parametrize("u,expected_status_code", [
    ('rando', 403),
    ('org_member', 403),
    ('org_admin', 201),
    ('admin', 201)
])
@pytest.mark.django_db()
def test_create_project(post, organization, org_admin, org_member, admin, rando, u, expected_status_code):
    if u == 'rando':
        u = rando
    elif u == 'org_member':
        u = org_member
    elif u == 'org_admin':
        u = org_admin
    elif u == 'admin':
        u = admin

    result = post(reverse('api:project_list'), {
        'name': 'Project',
        'organization': organization.id,
    }, u)
    print(result.data)
    assert result.status_code == expected_status_code
    if expected_status_code == 201:
        assert Project.objects.filter(name='Project', organization=organization).exists()


@pytest.mark.django_db()
def test_create_project_null_organization(post, organization, admin):
    post(reverse('api:project_list'), { 'name': 't', 'organization': None}, admin, expect=201)


@pytest.mark.django_db()
def test_create_project_null_organization_xfail(post, organization, org_admin):
    post(reverse('api:project_list'), { 'name': 't', 'organization': None}, org_admin, expect=403)


@pytest.mark.django_db()
def test_patch_project_null_organization(patch, organization, project, admin):
    patch(reverse('api:project_detail', args=(project.id,)), { 'name': 't', 'organization': organization.id}, admin, expect=200)


@pytest.mark.django_db()
def test_patch_project_null_organization_xfail(patch, project, org_admin):
    patch(reverse('api:project_detail', args=(project.id,)), { 'name': 't', 'organization': None}, org_admin, expect=400)


@pytest.mark.django_db
def test_cannot_schedule_manual_project(project, admin_user, post):
    response = post(
        reverse('api:project_schedules_list', args=(project.pk,)),
        {"name": "foo", "description": "", "enabled": True,
            "rrule": "DTSTART:20160926T040000Z RRULE:FREQ=HOURLY;INTERVAL=1",
            "extra_data": {}}, admin_user, expect=400)
    assert 'Manual' in response.data['unified_job_template'][0]
