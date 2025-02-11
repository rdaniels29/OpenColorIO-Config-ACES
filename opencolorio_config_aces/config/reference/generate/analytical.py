# SPDX-License-Identifier: BSD-3-Clause
# Copyright Contributors to the OpenColorIO Project.
"""
*aces-dev* Analytical Reference Config Generator
================================================

Defines various objects related to the generation of the analytical *aces-dev*
reference *OpenColorIO* config.
"""

import itertools
import logging

from opencolorio_config_aces.config.generation import (
    ConfigData, colorspace_factory, generate_config)
from opencolorio_config_aces.config.reference.discover.graph import (
    NODE_NAME_SEPARATOR)
from opencolorio_config_aces.config.reference import (
    ColorspaceDescriptionStyle, build_aces_conversion_graph,
    classify_aces_ctl_transforms, conversion_path,
    discover_aces_ctl_transforms, filter_nodes, filter_ctl_transforms,
    node_to_ctl_transform)
from opencolorio_config_aces.config.reference.generate.config import (
    ACES_CONFIG_BUILTIN_TRANSFORM_NAME_SEPARATOR,
    ACES_CONFIG_COLORSPACE_NAME_SEPARATOR,
    ACES_CONFIG_OUTPUT_ENCODING_COLORSPACE, ACES_CONFIG_REFERENCE_COLORSPACE,
    beautify_display_name, beautify_name, ctl_transform_to_colorspace)
from opencolorio_config_aces.utilities import required

__author__ = 'OpenColorIO Contributors'
__copyright__ = 'Copyright Contributors to the OpenColorIO Project.'
__license__ = 'New BSD License - https://opensource.org/licenses/BSD-3-Clause'
__maintainer__ = 'OpenColorIO Contributors'
__email__ = 'ocio-dev@lists.aswf.io'
__status__ = 'Production'

__all__ = [
    'VIEW_NAME_SUBSTITUTION_PATTERNS', 'beautify_view_name',
    'create_builtin_transform', 'node_to_builtin_transform',
    'node_to_colorspace', 'generate_config_aces'
]

VIEW_NAME_SUBSTITUTION_PATTERNS = {
    '\\(100 nits\\) dim': '',
    '\\(100 nits\\)': '',
    '\\(48 nits\\)': '',
    f'Output{ACES_CONFIG_COLORSPACE_NAME_SEPARATOR}': '',
}
"""
*OpenColorIO* view name substitution patterns.

VIEW_NAME_SUBSTITUTION_PATTERNS : dict
"""


def beautify_view_name(name):
    """
    Beautifies given *OpenColorIO* view name by applying in succession the
    relevant patterns.

    Parameters
    ----------
    name : unicode
        *OpenColorIO* view name to beautify.

    Returns
    -------
    unicode
        Beautified *OpenColorIO* view name.

    Examples
    --------
    >>> beautify_view_name('Rec. 709 (100 nits) dim')
    'Rec. 709'
    """

    return beautify_name(name, VIEW_NAME_SUBSTITUTION_PATTERNS)


@required('OpenColorIO')
def create_builtin_transform(style):
    """
    Creates an *OpenColorIO* builtin transform for given style.

    If the style does not exist, a placeholder transform is used in place
    of the builtin transform.

    Parameters
    ----------
    style : unicode
        *OpenColorIO* builtin transform style

    Returns
    -------
    BuiltinTransform
        *OpenColorIO* builtin transform for given style.
    """

    import PyOpenColorIO as ocio

    builtin_transform = ocio.BuiltinTransform()

    try:
        builtin_transform.setStyle(style)
    except ocio.Exception:
        logging.warning(f'{style} style is not defined, '
                        f'using a placeholder "FileTransform" instead!')
        builtin_transform = ocio.FileTransform()
        builtin_transform.setSrc(style)

    return builtin_transform


@required('NetworkX')
@required('OpenColorIO')
def node_to_builtin_transform(graph, node, direction='Forward'):
    """
    Generates the *OpenColorIO* builtin transform for given *aces-dev*
    conversion graph node.

    Parameters
    ----------
    graph : DiGraph
        *aces-dev* conversion graph.
    node : unicode
        Node name to generate the *OpenColorIO* builtin transform for.
    direction : unicode, optional
        {'Forward', 'Reverse'},

    Returns
    -------
    BuiltinTransform
        *OpenColorIO* builtin transform.
    """

    import PyOpenColorIO as ocio
    from networkx.exception import NetworkXNoPath

    try:
        transform_styles = []

        path = (node, ACES_CONFIG_REFERENCE_COLORSPACE)
        path = path if direction.lower() == 'forward' else reversed(path)
        path = conversion_path(graph, *path)

        if not path:
            return

        verbose_path = " --> ".join(
            dict.fromkeys(itertools.chain.from_iterable(path)))
        logging.debug(f'Creating "BuiltinTransform" with {verbose_path} path.')

        for edge in path:
            source, target = edge
            transform_styles.append(
                f'{source.split(NODE_NAME_SEPARATOR)[-1]}'
                f'{ACES_CONFIG_BUILTIN_TRANSFORM_NAME_SEPARATOR}'
                f'{target.split(NODE_NAME_SEPARATOR)[-1]}')

        if len(transform_styles) == 1:
            builtin_transform = create_builtin_transform(transform_styles[0])

            return builtin_transform
        else:
            group_transform = ocio.GroupTransform()

            for transform_style in transform_styles:
                builtin_transform = create_builtin_transform(transform_style)
                group_transform.appendTransform(builtin_transform)

            return group_transform

    except NetworkXNoPath:
        logging.debug(
            f'No path to {ACES_CONFIG_REFERENCE_COLORSPACE} for {node}!')


def node_to_colorspace(graph,
                       node,
                       describe=ColorspaceDescriptionStyle.LONG_UNION):
    """
    Generates the *OpenColorIO* colorspace for given *aces-dev* conversion
    graph node.

    Parameters
    ----------
    graph : DiGraph
        *aces-dev* conversion graph.
    node : unicode
        Node name to generate the *OpenColorIO* colorspace for.
    describe : int, optional
        Any value from the
        :class:`opencolorio_config_aces.ColorspaceDescriptionStyle` enum.

    Returns
    -------
    ColorSpace
        *OpenColorIO* colorspace.
    """

    ctl_transform = node_to_ctl_transform(graph, node)

    colorspace = ctl_transform_to_colorspace(
        ctl_transform,
        describe=describe,
        to_reference=node_to_builtin_transform(graph, node),
        from_reference=node_to_builtin_transform(graph, node, 'Reverse'))

    return colorspace


@required('OpenColorIO')
def generate_config_aces(config_name=None,
                         validate=True,
                         describe=ColorspaceDescriptionStyle.LONG_UNION,
                         filterers=None,
                         additional_data=False):
    """
    Generates the *aces-dev* reference implementation *OpenColorIO* Config
    using the analytical *Graph* method.

    The Config generation is driven entirely from the *aces-dev* conversion
    graph. The config generated, while not usable because of the missing
    *OpenColorIO* *BuiltinTransforms*, provides an exact mapping with the
    *aces-dev* *CTL* transforms, and, for example, uses the
    *Output Color Encoding Specification* (OCES) colourspace.

    Parameters
    ----------
    config_name : unicode, optional
        *OpenColorIO* config file name, if given the config will be written to
        disk.
    validate : bool, optional
        Whether to validate the config.
    describe : int, optional
        Any value from the
        :class:`opencolorio_config_aces.ColorspaceDescriptionStyle` enum.
    filterers : array_like, optional
        List of callables used to filter the *ACES* *CTL* transforms, each
        callable takes an *ACES* *CTL* transform as argument and returns
        whether to include or exclude the *ACES* *CTL* transform as a bool.
    additional_data : bool, optional
        Whether to return additional data.

    Returns
    -------
    Config or tuple
        *OpenColorIO* config or tuple of *OpenColorIO* config,
        :class:`opencolorio_config_aces.ConfigData` class instance and dict of
        *OpenColorIO* colorspaces and
        :class:`opencolorio_config_aces.config.reference.CTLTransform` class
        instances.
    """

    import PyOpenColorIO as ocio

    ctl_transforms = discover_aces_ctl_transforms()
    classified_ctl_transforms = classify_aces_ctl_transforms(ctl_transforms)
    filtered_ctl_transforms = filter_ctl_transforms(classified_ctl_transforms,
                                                    filterers)

    graph = build_aces_conversion_graph(filtered_ctl_transforms)

    colorspaces_to_ctl_transforms = {}
    colorspaces = []
    displays = set()
    views = []

    scene_reference_colorspace = colorspace_factory(
        f'CSC - {ACES_CONFIG_REFERENCE_COLORSPACE}',
        'ACES',
        description='The "Academy Color Encoding System" reference colorspace.'
    )

    display_reference_colorspace = colorspace_factory(
        f'CSC - {ACES_CONFIG_OUTPUT_ENCODING_COLORSPACE}',
        'ACES',
        description='The "Output Color Encoding Specification" colorspace.',
        from_reference=node_to_builtin_transform(
            graph, ACES_CONFIG_OUTPUT_ENCODING_COLORSPACE, 'Reverse'))

    raw_colorspace = colorspace_factory(
        'Utility - Raw',
        'Utility',
        description='The utility "Raw" colorspace.',
        is_data=True)

    colorspaces += [
        scene_reference_colorspace,
        display_reference_colorspace,
        raw_colorspace,
    ]

    for family in ('csc', 'input_transform', 'lmt', 'output_transform'):
        family_colourspaces = []
        for node in filter_nodes(graph, [lambda x: x.family == family]):
            if node in (ACES_CONFIG_REFERENCE_COLORSPACE,
                        ACES_CONFIG_OUTPUT_ENCODING_COLORSPACE):
                continue

            colorspace = node_to_colorspace(graph, node, describe)

            family_colourspaces.append(colorspace)

            if family == 'output_transform':
                display = beautify_display_name(
                    node_to_ctl_transform(graph, node).genus)
                displays.add(display)
                view = beautify_view_name(colorspace.getName())
                views.append({
                    'display': display,
                    'view': view,
                    'colorspace': colorspace.getName()
                })

            if additional_data:
                colorspaces_to_ctl_transforms[colorspace] = (
                    node_to_ctl_transform(graph, node))

        colorspaces += family_colourspaces

    views = sorted(views, key=lambda x: (x['display'], x['view']))
    displays = sorted(list(displays))
    if 'sRGB' in displays:
        displays.insert(0, displays.pop(displays.index('sRGB')))

    for display in displays:
        view = beautify_view_name(raw_colorspace.getName())
        views.append({
            'display': display,
            'view': view,
            'colorspace': raw_colorspace.getName()
        })

    data = ConfigData(
        description='The "Academy Color Encoding System" reference config.',
        roles={
            ocio.ROLE_SCENE_LINEAR: 'CSC - ACEScg',
        },
        colorspaces=colorspaces,
        views=views,
        active_displays=displays,
        active_views=list(dict.fromkeys([view['view'] for view in views])),
        file_rules=[{
            'name': 'Default',
            'colorspace': 'CSC - ACEScg'
        }],
        profile_version=2)

    config = generate_config(data, config_name, validate)

    if additional_data:
        return config, data, colorspaces_to_ctl_transforms
    else:
        return config


if __name__ == '__main__':
    import os
    import opencolorio_config_aces

    logging.basicConfig()
    logging.getLogger().setLevel(logging.INFO)

    build_directory = os.path.join(opencolorio_config_aces.__path__[0], '..',
                                   'build')

    if not os.path.exists(build_directory):
        os.makedirs(build_directory)

    config, data, colorspaces = generate_config_aces(
        config_name=os.path.join(build_directory,
                                 'config-aces-reference-analytical.ocio'),
        additional_data=True)

    for ctl_transform in colorspaces.values():
        print(ctl_transform.aces_transform_id)
