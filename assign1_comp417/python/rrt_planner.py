#!/usr/bin/python
import sys
import time
import pickle
import numpy as np
import random
import cv2

from itertools import product
from math import cos, sin, pi, sqrt, atan, pi

from plotting_utils import draw_plan
from priority_queue import priority_dict

class State(object):
    """
    2D state. 
    """
    
    def __init__(self, x, y, parent):
        """
        x represents the columns on the image and y represents the rows,
        Both are presumed to be integers
        """
        self.x = x
        self.y = y
        self.parent = parent
        self.children = []

        
    def __eq__(self, state):
        """
        When are two states equal?
        """    
        return state and self.x == state.x and self.y == state.y 

    def __hash__(self):
        """
        The hash function for this object. This is necessary to have when we
        want to use State objects as keys in dictionaries
        """
        return hash((self.x, self.y))
    
    def euclidean_distance(self, state):
        assert (state)
        return sqrt((state.x - self.x)**2 + (state.y - self.y)**2)
    
class RRTPlanner(object):
    """
    Applies the RRT algorithm on a given grid world
    """
    
    def __init__(self, world):
        # (rows, cols, channels) array with values in {0,..., 255}
        self.world = world

        # (rows, cols) binary array. Cell is 1 iff it is occupied
        self.occ_grid = self.world[:,:,0]
        self.occ_grid = (self.occ_grid == 0).astype('uint8')
        
    def state_is_free(self, state):
        """
        Does collision detection. Returns true iff the state and its nearby 
        surroundings are free.
        """
        return (self.occ_grid[state.y-5:state.y+5, state.x-5:state.x+5] == 0).all()


    def sample_state(self):
        """
        Sample a new state uniformly randomly on the image. 
        """
        #TODO: make sure you're not exceeding the row and columns bounds
        # x must be in {0, cols-1} and y must be in {0, rows -1}
        
        x = random.randint(0, self.world.shape[0] - 1)
        y = random.randint(0, self.world.shape[1] - 1)
        
        while not self.state_is_free(State(x,y,None)):
            x = random.randint(0, self.world.shape[0] - 1)
            y = random.randint(0, self.world.shape[1] - 1)
        return State(x, y, None)
           

    def _follow_parent_pointers(self, state):
        """
        Returns the path [start_state, ..., destination_state] by following the
        parent pointers.
        """
        
        curr_ptr = state
        path = [state]
        
        while curr_ptr is not None:
            path.append(curr_ptr)
            curr_ptr = curr_ptr.parent

        # return a reverse copy of the path (so that first state is starting state)
        return path[::-1]


    def find_closest_state(self, tree_nodes, state):
        min_dist = float("Inf")
        closest_state = None
        for node in tree_nodes:
            dist = node.euclidean_distance(state)  
            if dist < min_dist:
                closest_state = node
                min_dist = dist

        return closest_state

    def steer_towards(self, s_nearest, s_rand, max_radius):
        """
        Returns a new state s_new whose coordinates x and y
        are decided as follows:
        
        If s_rand is within a circle of max_radius from s_nearest
        then s_new.x = s_rand.x and s_new.y = s_rand.y
        
        Otherwise, s_rand is farther than max_radius from s_nearest. 
        In this case we place s_new on the line from s_nearest to
        s_rand, at a distance of max_radius away from s_nearest.
        
        """

        #TODO: populate x and y properly according to the description above.
        #Note: x and y are integers and they should be in {0, ..., cols -1}
        # and {0, ..., rows -1} respectively
        s_new = State(0, 0, s_nearest)
        
        # s_rand and s_nearest are within max_radius of each other
        if s_rand.euclidean_distance(s_nearest) <= max_radius:
            s_new.x = s_rand.x
            s_new.y = s_rand.y
        
        # interpolate using trigonometry
        else:
            # get the angle
            try:
                angle = atan((s_rand.y - s_nearest.y)/(s_rand.x - s_nearest.x))
            except ZeroDivisionError:
                s_new.x = s_nearest.x
                s_new.y = s_nearest.y + max_radius

                s_new.x = int(s_new.x)
                s_new.y = int(s_new.y)
                return s_new

            # add offsets to the angle, if necessary, depending on the quadrant
            # that the s_rand position is in
            if s_rand.x >= s_nearest.x:
                # to the right and top of s_nearest, no offset
                if s_rand.y >= s_nearest.y:
                    pass
                # to the right and bottom of s_nearest, invert sign
                else:
                    angle = -angle
            else:
                # to the left and top of s_nearest, add pi rad
                if s_rand.y >= s_nearest.y:
                    angle = angle + pi
                # to the left and bottom of s_nearest, add 2pi rad
                else:
                    angle = angle + 2 * pi

            # take the cosine and sine of the angle, multiply by the radius
            s_new.x = s_nearest.x + cos(angle) * max_radius
            s_new.y = s_nearest.y + sin(angle) * max_radius

            s_new.x = int(s_new.x)
            s_new.y = int(s_new.y)

        return s_new


    def path_is_obstacle_free(self, s_from, s_to):
        """
        Returns true iff the line path from s_from to s_to
        is free
        """
        assert (self.state_is_free(s_from))
        
        if not (self.state_is_free(s_to)):
            return False

        # set the max checks and angle variable
        max_checks = 10
        angle = 0
        s_new = State(0,0,None) # dummy variable

        # extract the angle
        try:
            angle = atan((s_to.y - s_from.y)/(s_to.x - s_from.x))

            # add offsets to the angle, if necessary, depending on the quadrant
            # that the s_to position is in
            if s_to.x >= s_from.x:
                # to the right and top of s_from, no offset
                if s_to.y >= s_from.y:
                    pass
                # to the right and bottom of s_from, invert sign
                else:
                    angle = -angle
            else:
                # to the left and top of s_from, add pi rad
                if s_to.y >= s_from.y:
                    angle = angle + pi
                # to the left and bottom of s_from, add 2pi rad
                else:
                    angle = angle + 2 * pi

        # moving straight up
        except ZeroDivisionError:
            for i in xrange(max_checks):
                distance = float(i)/max_checks * s_from.euclidean_distance(s_to)

                s_new.x = s_from.x
                s_new.y = s_from.y + distance

                s_new.x = int(s_new.x)
                s_new.y = int(s_new.y)

                if self.state_is_free(s_new):
                    continue
                return False
            return True

        # all other directions
        for i in xrange(max_checks):
            # TODO: check if the interpolated state that is float(i)/max_checks * dist(s_from, s_new)
            # away on the line from s_from to s_new is free or not. If not free return False
            
            distance = float(i)/max_checks * s_from.euclidean_distance(s_to)

            # take the cosine and sine of the angle, multiply by the radius
            s_new.x = s_from.x + cos(angle) * distance
            s_new.y = s_from.y + sin(angle) * distance

            s_new.x = int(s_new.x)
            s_new.y = int(s_new.y)

            if self.state_is_free(s_new):
                continue
            return False
            
        # Otherwise the line is free, so return true
        return True

    
    def plan(self, start_state, dest_state, max_num_steps, max_steering_radius, dest_reached_radius):
        """
        Returns a path as a sequence of states [start_state, ..., dest_state]
        if dest_state is reachable from start_state. Otherwise returns [start_state].
        Assume both source and destination are in free space.
        """
        assert (self.state_is_free(start_state))
        assert (self.state_is_free(dest_state))

        # The set containing the nodes of the tree
        tree_nodes = set()
        tree_nodes.add(start_state)
        
        # image to be used to display the tree
        img = np.copy(self.world)

        plan = [start_state]
        
        for step in xrange(max_num_steps):

            # TODO: Use the methods of this class as in the slides to
            # compute s_new

            s_rand = self.sample_state()
            s_nearest = self.find_closest_state(tree_nodes, s_rand)
            s_new = self.steer_towards(s_nearest, s_rand, max_steering_radius)
            
            if self.path_is_obstacle_free(s_nearest, s_new):
                tree_nodes.add(s_new)
                s_nearest.children.append(s_new)

                # If we approach the destination within a few pixels
                # we're done. Return the path.
                if s_new.euclidean_distance(dest_state) < dest_reached_radius:
                    dest_state.parent = s_new
                    plan = self._follow_parent_pointers(dest_state)
                    break
                
                # plot the new node and edge
                cv2.circle(img, (s_new.x, s_new.y), 2, (0,0,0))
                cv2.line(img, (s_nearest.x, s_nearest.y), (s_new.x, s_new.y), (255,0,0))

            # Keep showing the image for a bit even
            # if we don't add a new node and edge
            cv2.imshow('image', img)
            #cv2.waitKey(10)

        draw_plan(img, plan, bgr=(0,0,255), thickness=2)
        cv2.waitKey(0)
        return [start_state]


    
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print "Usage: rrt_planner.py occupancy_grid.pkl"
        sys.exit(1)

    pkl_file = open(sys.argv[1], 'rb')
    # world is a numpy array with dimensions (rows, cols, 3 color channels)
    world = pickle.load(pkl_file)
    pkl_file.close()

    rrt = RRTPlanner(world)

    start_state = State(10, 10, None)
    dest_state = State(500, 100, None)

    max_num_steps = 1000     # max number of nodes to be added to the tree 
    max_steering_radius = 30 # pixels
    dest_reached_radius = 50 # pixels
    plan = rrt.plan(start_state,
                    dest_state,
                    max_num_steps,
                    max_steering_radius,
                    dest_reached_radius)
    #draw_plan(world, plan)
    
