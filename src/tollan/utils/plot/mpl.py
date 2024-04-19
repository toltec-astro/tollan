import matplotlib.pyplot as plt


# https://gist.github.com/digitalsignalperson/546e80ae1965b83df0a82ba12ae8aac7
def move_axes(ax, ax_new, remove=True):
    """Move an Axes object from a figure to a new one."""
    # get a reference to the old figure context so we can release it
    old_fig = ax.figure

    # remove the Axes from it's original Figure context
    ax.remove()

    # set the pointer from the Axes to the new figure
    ax.figure = ax_new.figure

    # add the Axes to the registry of axes for the figure
    ax_new.figure.axes.append(ax)
    # twice, I don't know why...
    ax_new.figure.add_axes(ax)

    # then to actually show the Axes in the new figure we have to make
    # a subplot with the positions etc for the Axes to go, so make a
    # subplot which will have a dummy Axes

    # then copy the relevant data from the dummy to the ax
    ax.set_position(ax_new.get_position())

    # then remove the dummy
    ax_new.remove()

    # close the figure the original axis was bound to
    if remove:
        plt.close(old_fig)
    return ax
