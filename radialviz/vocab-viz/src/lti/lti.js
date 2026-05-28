export function getFieldsFromUrl() {
    const params = new URLSearchParams(window.location.search);
    const launch_id = params.get('launch_id');
    if (!launch_id) return { 'launch_id': '', 'is_lti_context': false, 'is_student': false };
    const student = params.get('is_student') === 'True';
    return { launch_id, 'is_lti_context': true, 'is_student': student };
}
