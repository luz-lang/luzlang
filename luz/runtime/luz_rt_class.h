/*
 * luz_rt_class.h — Runtime class registry for compiled Luz programs.
 *
 * Provides a dynamic registry for class metadata (attribute names, method
 * function pointers, inheritance chains) that the LLVM backend populates
 * at program startup, and dispatch helpers used by compiled method calls.
 */

#ifndef LUZ_RT_CLASS_H
#define LUZ_RT_CLASS_H

#include "luz_runtime.h"
#include <stdint.h>

/* Register a class in the runtime registry.
   Must be called before any objects of this class are created. */
void luz_rt_register_class(uint32_t class_id, const char *name,
                            size_t attr_count);

/* Set the parent class of a registered class (0 = no parent). */
void luz_rt_set_parent(uint32_t class_id, uint32_t parent_id);

/* Register an attribute name at a specific slot index. */
void luz_rt_register_attr(uint32_t class_id, int32_t slot_index,
                           const char *name);

/* Register a method function pointer for a class.
   nparams: total parameter count including self. */
void luz_rt_register_method(uint32_t class_id, const char *name,
                              void *fn, int32_t nparams);

/* Create a new object of the given class_id (calls luz_obj_new internally). */
luz_value_t luz_rt_new_obj(uint32_t class_id);

/* Call a user-defined method on an object by name.
   args: pointer to an array of nargs luz_value_t arguments (NOT including self).
   Pass NULL for args when nargs == 0. */
luz_value_t luz_rt_obj_call(luz_value_t obj, const char *name,
                             luz_value_t *args, int32_t nargs);

/* isinstance check — walks the inheritance chain.
   Returns a bool luz_value_t. */
luz_value_t luz_rt_isinstance(luz_value_t obj, uint32_t class_id);

#endif /* LUZ_RT_CLASS_H */
