export function getFieldsFromUrl() {
    const params = new URLSearchParams(window.location.search);
    const launch_id = params.get('launch_id');
    const deployment_id = params.get('deployment_id');
    const deployment_url = params.get('deployment_url');
    if (!launch_id) return { 'launch_id': '', 'is_lti_context': false, 'is_student': false };
    const student = params.get('is_student') === 'True';
    return { launch_id, 'is_lti_context': true, 'is_student': student, deployment_url, deployment_id };
}
