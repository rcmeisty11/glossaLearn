-- partially AI generated
INSERT INTO
    course (deployment_id)
VALUES
    ('1:1e075409ad624091d15a5fed6992a3d897a3cd4c');

INSERT INTO
    assignment (
        deployment_id,
        assignment_id,
        assignment_type,
        author,
        work,
        sentence_id
    )
VALUES
    (
        '1:1e075409ad624091d15a5fed6992a3d897a3cd4c',
        'assignment-1',
        'translation',
        'Galen',
        'Galens Work',
        'Sentence 1'
    ),
    (
        '1:1e075409ad624091d15a5fed6992a3d897a3cd4c',
        'assignment-2',
        'production',
        'Galen',
        'Galens Work',
        'Sentence 1'
    ),
    (
        '1:1e075409ad624091d15a5fed6992a3d897a3cd4c',
        'assignment-3',
        'perception',
        'Galen',
        'Galens Work',
        'Sentence 1'
    ),
    (
        '1:1e075409ad624091d15a5fed6992a3d897a3cd4c',
        'assignment-4',
        'translation',
        'Galen',
        'Galens Work',
        'Sentence 1'
    ),
    (
        '1:1e075409ad624091d15a5fed6992a3d897a3cd4c',
        'assignment-5',
        'production',
        'Galen',
        'Galens Work',
        'Sentence 1'
    );

INSERT INTO
    assignment_submission (
        deployment_id,
        student_id,
        assignment_id,
        assignment_artifact,
        grade
    )
VALUES
    (
        '1:1e075409ad624091d15a5fed6992a3d897a3cd4c',
        'c88538f96a56fca7682c138f00f4e1c0c9d05152',
        'assignment-1',
        'The quick brown fox jumps over the lazy dog.',
        94.50
    ),
    (
        '1:1e075409ad624091d15a5fed6992a3d897a3cd4c',
        'c88538f96a56fca7682c138f00f4e1c0c9d05152',
        'assignment-2',
        'https://cdn.example.com/audio/student101-assignment2.mp3',
        88.00
    ),
    (
        '1:1e075409ad624091d15a5fed6992a3d897a3cd4c',
        'c88538f96a56fca7682c138f00f4e1c0c9d05152',
        'assignment-3',
        'Student identified the correct phonemes.',
        NULL
    ),
    (
        '1:1e075409ad624091d15a5fed6992a3d897a3cd4c',
        'student-102',
        'assignment-1',
        'Lorem ipsum translated response.',
        97.00
    ),
    (
        '1:1e075409ad624091d15a5fed6992a3d897a3cd4c',
        'student-102',
        'assignment-4',
        'Another translation artifact.',
        NULL
    ),
    (
        '1:1e075409ad624091d15a5fed6992a3d897a3cd4c',
        'student-103',
        'assignment-5',
        'https://cdn.example.com/audio/student103-assignment5.mp3',
        91.25
    );