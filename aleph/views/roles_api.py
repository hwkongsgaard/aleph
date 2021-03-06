from flask import Blueprint, request
from werkzeug.exceptions import BadRequest
from apikit import obj_or_404, request_data, jsonify

from aleph.core import db
from aleph.events import log_event
from aleph.model import Role, Collection, Permission
from aleph.logic.permissions import update_permission
from aleph.data.validate import validate


blueprint = Blueprint('roles_api', __name__)


def check_visible(role):
    """Users should not see group roles which they are not a part of."""
    if request.authz.is_admin or role.id in request.authz.roles:
        return True
    return role.type == Role.USER


@blueprint.route('/api/1/roles', methods=['GET'])
def index():
    request.authz.require(request.authz.logged_in)
    users = []
    for role in Role.all():
        if not check_visible(role):
            continue
        data = role.to_dict()
        del data['email']
        users.append(data)
    return jsonify({'results': users, 'total': len(users)})


@blueprint.route('/api/1/roles/<int:id>', methods=['GET'])
def view(id):
    role = obj_or_404(Role.by_id(id))
    request.authz.require(request.authz.logged_in)
    request.authz.require(check_visible(role))
    data = role.to_dict()
    if role.id != request.authz.role.id:
        del data['email']
    return jsonify(data)


@blueprint.route('/api/1/roles/<int:id>', methods=['POST', 'PUT'])
def update(id):
    role = obj_or_404(Role.by_id(id))
    request.authz.require(request.authz.session_write())
    request.authz.require(role.id == request.authz.role.id)
    role.update(request_data())
    db.session.add(role)
    db.session.commit()
    log_event(request)
    return jsonify(role)


@blueprint.route('/api/1/collections/<int:collection>/permissions')
def permissions_index(collection):
    request.authz.require(request.authz.collection_write(collection))
    q = Permission.all()
    q = q.filter(Permission.collection_id == collection)
    permissions = []
    for permission in q.all():
        if check_visible(permission.role):
            permissions.append(permission)
    return jsonify({
        'total': len(permissions),
        'results': permissions
    })


@blueprint.route('/api/1/collections/<int:collection>/permissions',
                 methods=['POST', 'PUT'])
def permissions_update(collection):
    request.authz.require(request.authz.collection_write(collection))
    data = request_data()
    validate(data, 'permission.json#')

    role = Role.all().filter(Role.id == data['role']).first()
    collection = Collection.by_id(collection)
    if role is None or collection is None:
        raise BadRequest()
    request.authz.require(check_visible(role))

    perm = update_permission(role, collection, data['read'], data['write'])
    log_event(request)
    return jsonify({
        'status': 'ok',
        'updated': perm
    })
