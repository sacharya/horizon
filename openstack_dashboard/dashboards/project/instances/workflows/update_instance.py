# Copyright 2012 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
# All Rights Reserved.
#
# Copyright 2012 Nebula, Inc.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.


from django.utils.translation import ugettext_lazy as _

from horizon import exceptions
from horizon import forms
from horizon import workflows

from openstack_dashboard import api
from openstack_dashboard.utils import filters

INDEX_URL = "horizon:projects:instances:index"
ADD_USER_URL = "horizon:projects:instances:create_user"
INSTANCE_SEC_GROUP_SLUG = "update_security_groups"


class UpdateInstanceSecurityGroupsAction(workflows.MembershipAction):
    def __init__(self, request, *args, **kwargs):
        super(UpdateInstanceSecurityGroupsAction, self).__init__(request,
                                                                 *args,
                                                                 **kwargs)
        err_msg = _('Unable to retrieve security group list. '
                    'Please try again later.')
        context = args[0]
        instance_id = context.get('instance_id', '')

        default_role_name = self.get_default_role_field_name()
        self.fields[default_role_name] = forms.CharField(required=False)
        self.fields[default_role_name].initial = 'member'

        # Get list of available security groups
        all_groups = []
        try:
            all_groups = api.network.security_group_list(request)
        except Exception:
            exceptions.handle(request, err_msg)
        groups_list = [(group.id, group.name) for group in all_groups]

        instance_groups = []
        try:
            instance_groups = api.network.server_security_groups(request,
                                                                 instance_id)
        except Exception:
            exceptions.handle(request, err_msg)
        field_name = self.get_member_field_name('member')
        self.fields[field_name] = forms.MultipleChoiceField(required=False)
        self.fields[field_name].choices = groups_list
        self.fields[field_name].initial = [group.id
                                           for group in instance_groups]

    def handle(self, request, data):
        instance_id = data['instance_id']
        wanted_groups = map(filters.get_int_or_uuid, data['wanted_groups'])
        try:
            api.network.server_update_security_groups(request, instance_id,
                                                      wanted_groups)
        except Exception as e:
            exceptions.handle(request, str(e))
            return False
        return True

    class Meta(object):
        name = _("Security Groups")
        slug = INSTANCE_SEC_GROUP_SLUG


class UpdateInstanceSecurityGroups(workflows.UpdateMembersStep):
    action_class = UpdateInstanceSecurityGroupsAction
    help_text = _("Add and remove security groups to this instance "
                  "from the list of available security groups.")
    available_list_title = _("All Security Groups")
    members_list_title = _("Instance Security Groups")
    no_available_text = _("No security groups found.")
    no_members_text = _("No security groups enabled.")
    show_roles = False
    depends_on = ("instance_id",)
    contributes = ("wanted_groups",)

    def contribute(self, data, context):
        request = self.workflow.request
        if data:
            field_name = self.get_member_field_name('member')
            context["wanted_groups"] = request.POST.getlist(field_name)
        return context


class UpdateInstanceInfoAction(workflows.Action):
    name = forms.CharField(label=_("Name"),
                           max_length=255)

    def handle(self, request, data):
        try:
            api.nova.server_update(request,
                                   data['instance_id'],
                                   data['name'])
        except Exception:
            exceptions.handle(request, ignore=True)
            return False
        return True

    class Meta(object):
        name = _("Information")
        slug = 'instance_info'
        help_text = _("Edit the instance details.")


class UpdateInstanceInfo(workflows.Step):
    action_class = UpdateInstanceInfoAction
    depends_on = ("instance_id",)
    contributes = ("name",)


class UpdateMetadataAction(workflows.Action):
    def __init__(self, request, *args, **kwargs):
        super(UpdateMetadataAction, self).__init__(request,
                                                         *args,
                                                         **kwargs)

    def handle(self, request, data):
        instance_id = data['instance_id']
        metadata_list = data['metadata']
        meta = {}
        if metadata_list:
            for item in metadata_list:
                if "=" in item:
                    key, val = item.split("=")
                    meta[key] = val
        old_meta = {}
        try:
            server = api.nova.server_get(self.request, instance_id)
            old_meta = server.metadata
        except Exception:
            msg = _('Unable to retrieve instance details.')
            exceptions.handle(self.request, msg)

        delete_meta = dict((k,v) for k,v in old_meta.items() if k not in meta)
        update_meta =  dict((k,v) for k,v in meta.items() if k not in old_meta or meta[k] != old_meta[k])

        if update_meta:
            try:
                api.nova.server_update_meta(request, instance_id,
                                       update_meta)
            except Exception as e:
                exceptions.handle(request, str(e))

        if delete_meta:
            try:
                api.nova.server_delete_meta(request, instance_id,
                                       delete_meta)
            except Exception as e:
                exceptions.handle(request, str(e))
                return False

        return True

    metadata = forms.CharField(label=_("Instance Metadata"),
                           max_length=255,
                           required=False)

    class Meta(object):
        name = _("Metadata")
        slug = "instance_metadata"


class UpdateMetadata(workflows.UpdateMetadataStep):
    action_class = UpdateMetadataAction
    contributes = ("metadata",)

    def contribute(self, data, context):
        if data:
            post = self.workflow.request.POST
            context['metadata'] = post.getlist("metadata")
        return context


class UpdateInstance(workflows.Workflow):
    slug = "update_instance"
    name = _("Edit Instance")
    finalize_button_name = _("Save")
    success_message = _('Modified instance "%s".')
    failure_message = _('Unable to modify instance "%s".')
    success_url = "horizon:project:instances:index"
    default_steps = (UpdateInstanceInfo,
                     UpdateInstanceSecurityGroups,
                     UpdateMetadata)

    def format_status_message(self, message):
        return message % self.context.get('name', 'unknown instance')


# NOTE(kspear): nova doesn't support instance security group management
#               by an admin. This isn't really the place for this code,
#               but the other ways of special-casing this are even messier.
class AdminUpdateInstance(UpdateInstance):
    success_url = "horizon:admin:instances:index"
    default_steps = (UpdateInstanceInfo,)
